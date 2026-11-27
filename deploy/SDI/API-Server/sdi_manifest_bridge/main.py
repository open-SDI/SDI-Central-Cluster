"""
SDI Manifest Bridge API.

- /v1/render-bundle · /v1/apply-bundle : ETRI IaC + MALE Binding 번들(IaCMaleBundle) 경로. k8s/client.py 의 K8sClient 사용.
- /v1/apply · /deploy                  : 예전 단순 입력(Ansible) 경로. core/legacy_client.py 의 SDIClient 사용.
- 환경 변수 스위치는 settings.py 에 모여 있다.
"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager

import anyio.to_thread
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .core.enrichment import enrich_manifest
from .core.legacy_client import SDIClient
from .core.bundle import (IaCMaleBundle, validate_bundle, bundle_warnings, convert_bundle,
                          resource_summary, apply_levels, normalize_bundle)
from .core.consistency import annotate_resources, warning_strings, start_cache_refresher
from .settings import apply_precheck_enabled, bridge_threads
from .k8s.client import k8s_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 쿠버네티스 호출(동기)은 이벤트 루프가 아니라 스레드풀에서 돈다. 요청 하나가 API 서버 응답을
# 기다리는 동안 다른 요청을 받아 처리한다(동시 요청이 한 줄로 서지 않게).
# 스레드 수 = 동시에 진행할 수 있는 쿠버네티스 호출 수(BRIDGE_THREADS, 기본 64). anyio 기본값은 40.
BRIDGE_THREADS = bridge_threads()

# apply-bundle 사전 dry-run (BRIDGE_APPLY_PRECHECK=on, 기본 off, settings.apply_precheck_enabled).
# apply-bundle 은 단계별로 실제 적용하다 중간에 실패하면 앞 단계가 남은 채 PARTIAL_FAILURE 가 된다.
# on 이면 적용 전에 모든 리소스를 dry-run 으로 한 번 검사하고, 하나라도 틀리면 아무것도 적용하지 않고 422.
# 번들이 만드는 네임스페이스는 아직 없으므로 그 안 리소스의 "namespace not found" 는 통과로 본다.
# 응답 precheckMs = 검사에 걸린 시간.


@asynccontextmanager
async def lifespan(_app: FastAPI):
    anyio.to_thread.current_default_thread_limiter().total_tokens = BRIDGE_THREADS
    logger.info(f"thread pool for Kubernetes calls: {BRIDGE_THREADS}")
    start_cache_refresher()  # 카탈로그 · 예측표를 요청 밖에서 미리 · 주기적으로 읽음(consistency.py)
    yield


app = FastAPI(title="SDI Manifest Bridge API", version="0.4.22", lifespan=lifespan)
sdi_client = SDIClient()

# 예전 단순 입력 경로: Ansible 이 호출하는 주소(/v1/apply)와 같은 기능의 /deploy
@app.post("/v1/apply")
@app.post("/deploy")
async def deploy(request: Request):
    try:
        user_input = await request.json()
        logger.info(f"Received deployment request: {user_input}")

        # 3개 리소스(Deployment, MaleWorkload, PropagationPolicy) 생성
        resources = await run_in_threadpool(enrich_manifest, user_input)

        # 순서대로 적용
        results = await run_in_threadpool(sdi_client.apply_resources, resources)

        return {
            "status": "SUCCESS", # 앤시블이 기대하는 필드명
            "message": "Deployment process completed",
            "results": results,
            "resource": {"name": resources[0]['metadata']['name']} if resources else {}
        }
    except Exception as e:
        logger.error(f"Deployment failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# --- ETRI IaC + MALE Binding 번들 API (Issue #1 합의) ---------------------
# render-bundle: 검증 + 리소스 렌더링 + dry-run만 수행 (클러스터 변경 없음)
# apply-bundle : 검증 후 합의된 순서대로 실제 적용
# 검증은 번들 단위 all-or-nothing: 에러가 하나라도 있으면 전체 거부

def _render(bundle: IaCMaleBundle):
    """공통 경로: 검증 실패 시 HTTPException(400), 성공 시 적용 순서의 리소스 목록 반환."""
    errors = validate_bundle(bundle)
    if errors:
        logger.warning(f"Bundle '{bundle.bundleId}' rejected: {errors}")
        raise HTTPException(status_code=400, detail={
            "status": "REJECTED",
            "bundleId": bundle.bundleId,
            "errors": errors,
        })
    return convert_bundle(bundle)


def _render_annotated(bundle: IaCMaleBundle):
    """_render + 분류 · 경고 annotation. 둘 다 카탈로그 · 예측표를 동기로 읽으므로 스레드풀에서 부른다."""
    resources = _render(bundle)
    # 분류 · 경고도 협의 규격 칸을 내부 칸으로 옮긴 사본으로 본다(criticality · rtSpec · placement 등)
    return resources, annotate_resources(normalize_bundle(bundle)[0], resources)


async def _apply_all(resources, dry_run: bool = False):
    """리소스들을 동시에 적용하고 입력 순서대로 (리소스, 예외 또는 None) 목록을 돌려준다."""
    async def one(res):
        try:
            await run_in_threadpool(k8s_client.apply, res, dry_run=dry_run)
            return res, None
        except Exception as e:  # 호출별 실패는 결과로 모은다
            return res, e
    return await asyncio.gather(*(one(res) for res in resources))


def _ns_missing_only(res, err, new_namespaces) -> bool:
    """번들이 만드는 네임스페이스가 아직 없어서 난 dry-run 실패인지."""
    ns = (res.get("metadata") or {}).get("namespace") or "default"
    if ns not in new_namespaces or getattr(err, "status", None) != 404:
        return False
    text = str(getattr(err, "body", "") or err).replace('\\"', '"')  # 응답 JSON 본문은 따옴표가 \" 로 옴
    return f'namespaces "{ns}" not found' in text


async def _precheck(resources):
    """적용 전 dry-run. (통과 여부, 리소스별 결과, 걸린 ms)"""
    new_ns = {(r.get("metadata") or {}).get("name") for r in resources if r.get("kind") == "Namespace"}
    t0 = time.monotonic()
    ok, results = True, []
    for res, err in await _apply_all(resources, dry_run=True):
        kind = res.get("kind")
        name = res.get("metadata", {}).get("name")
        if err is None:
            results.append({"kind": kind, "name": name, "status": "valid"})
        elif _ns_missing_only(res, err, new_ns):
            results.append({"kind": kind, "name": name, "status": "valid-after-namespace"})
        else:
            ok = False
            results.append({"kind": kind, "name": name, "status": "invalid", "error": str(err)})
    return ok, results, round((time.monotonic() - t0) * 1000, 1)


@app.post("/v1/render-bundle")
async def render_bundle(bundle: IaCMaleBundle):
    logger.info(f"Received render-bundle request: bundleId={bundle.bundleId}")
    resources, consistency_warnings = await run_in_threadpool(_render_annotated, bundle)

    # dry-run 은 클러스터를 바꾸지 않으므로 순서와 무관하게 한꺼번에 검사한다.
    # 번들이 함께 만드는 네임스페이스가 아직 없어서 난 404 는 apply 사전 검사(_precheck)처럼 통과로 본다
    new_ns = {(r.get("metadata") or {}).get("name") for r in resources if r.get("kind") == "Namespace"}
    dry_run_results = []
    ok = True
    for res, err in await _apply_all(resources, dry_run=True):
        kind = res.get("kind")
        name = res.get("metadata", {}).get("name")
        if err is None:
            dry_run_results.append({"kind": kind, "name": name, "status": "valid"})
        elif _ns_missing_only(res, err, new_ns):
            dry_run_results.append({"kind": kind, "name": name, "status": "valid-after-namespace"})
        else:
            ok = False
            dry_run_results.append({"kind": kind, "name": name, "status": "invalid",
                                    "error": str(err)})

    body = {
        "status": "RENDERED" if ok else "FAILED",
        "bundleId": bundle.bundleId,
        "missionId": bundle.missionId,
        "resources": resource_summary(resources),
        "dryRun": dry_run_results,
        "warnings": bundle_warnings(bundle, check_devices=True) + warning_strings(consistency_warnings),
    }
    return body if ok else JSONResponse(status_code=422, content=body)


@app.post("/v1/apply-bundle")
async def apply_bundle(bundle: IaCMaleBundle):
    logger.info(f"Received apply-bundle request: bundleId={bundle.bundleId}")
    resources, consistency_warnings = await run_in_threadpool(_render_annotated, bundle)

    precheck_ms = None
    if apply_precheck_enabled():
        ok, dry_run_results, precheck_ms = await _precheck(resources)
        logger.info(f"apply-bundle '{bundle.bundleId}' precheck ok={ok} {precheck_ms}ms")
        if not ok:
            return JSONResponse(status_code=422, content={
                "status": "PRECHECK_FAILED",
                "bundleId": bundle.bundleId,
                "missionId": bundle.missionId,
                "applied": [],
                "dryRun": dry_run_results,
                "precheckMs": precheck_ms,
                "warnings": bundle_warnings(bundle) + warning_strings(consistency_warnings),
            })

    # 합의된 단계 순서는 지키고, 같은 단계 안의 리소스는 동시에 적용한다.
    # (MaleWorkload 단계가 끝난 뒤 PropagationPolicy 단계 → 스케줄러가 등급 · 의도를 읽을 수 있음)
    applied, skipped = [], []
    failed, also_failed = None, []
    levels = apply_levels(resources)
    for i, level in enumerate(levels):
        for res, err in await _apply_all(level):
            kind = res.get("kind")
            name = res.get("metadata", {}).get("name")
            if err is None:
                applied.append({"kind": kind, "name": name, "status": "applied"})
                continue
            logger.error(f"apply-bundle '{bundle.bundleId}' failed at {kind}/{name}: {err}")
            entry = {"kind": kind, "name": name, "error": str(err)}
            if failed is None:
                failed = entry
            else:
                also_failed.append(entry)
        if failed:
            # 순서 보장을 위해 실패한 단계에서 중단하고 다음 단계 리소스는 건너뜀
            skipped = resource_summary([r for later in levels[i + 1:] for r in later])
            break

    if failed:
        content = {
            "status": "PARTIAL_FAILURE",
            "bundleId": bundle.bundleId,
            "applied": applied,
            "failed": failed,
            "skipped": skipped,
        }
        if also_failed:
            content["alsoFailed"] = also_failed
        if precheck_ms is not None:
            content["precheckMs"] = precheck_ms
        return JSONResponse(status_code=500, content=content)

    body = {
        "status": "SUCCESS",
        "bundleId": bundle.bundleId,
        "missionId": bundle.missionId,
        "applied": applied,
        "warnings": bundle_warnings(bundle) + warning_strings(consistency_warnings),
    }
    if precheck_ms is not None:
        body["precheckMs"] = precheck_ms
    return body


@app.get("/health")
def health():
    return {"status": "ok"}
