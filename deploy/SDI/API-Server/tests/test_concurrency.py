"""동기 쿠버네티스 호출이 이벤트 루프를 막지 않는지 (클러스터 불필요).

느린 가짜 클라이언트(호출마다 time.sleep, 실제 API 서버처럼 스레드를 막음)로 바꿔 끼우고
ASGI 앱을 직접 호출한다. 예전 코드(async 핸들러 안 동기 호출)면 32건이 한 줄로 처리되어
32 x 단건 시간이 걸린다.
"""
import asyncio
import importlib
import json
import threading
import time
from unittest import mock

import pytest

from tests.test_bundle import etri_example_bundle, patrol_robot_bundle

DELAY = 0.1  # 가짜 API 호출 하나의 지연(초)


def _import_main():
    # main 은 import 할 때 kubeconfig 를 읽는다. 시험에서는 읽지 않게 막는다.
    with mock.patch("kubernetes.config.load_kube_config"), \
            mock.patch("kubernetes.config.load_incluster_config"):
        return importlib.import_module("sdi_manifest_bridge.main")


main = _import_main()


class SlowFakeK8s:
    def __init__(self, delay=DELAY, fail=None):
        self.delay = delay
        self.fail = fail or set()  # 실패시킬 (kind, name)
        self.lock = threading.Lock()
        self.calls = []  # (kind, name, dry_run, start, end)

    def apply(self, manifest, dry_run=False):
        start = time.monotonic()
        time.sleep(self.delay)  # 블로킹 I/O 흉내
        end = time.monotonic()
        key = (manifest["kind"], manifest["metadata"]["name"])
        with self.lock:
            self.calls.append((key[0], key[1], dry_run, start, end))
        if key in self.fail:
            raise RuntimeError(f"fake failure {key[0]}/{key[1]}")
        return {}


async def asgi_post(app, path, payload):
    """HTTP 서버 없이 ASGI 앱에 POST 한 건을 보낸다."""
    body = json.dumps(payload).encode()
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": b"", "root_path": "",
        "headers": [(b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode())],
        "client": ("127.0.0.1", 50000), "server": ("testserver", 80),
    }
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.sleep(30)
        return {"type": "http.disconnect"}

    status, chunks = None, []

    async def send(message):
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await app(scope, receive, send)
    raw = b"".join(chunks)
    return status, (json.loads(raw) if raw else None)


def run_concurrently(path, payloads):
    async def go():
        async with main.lifespan(main.app):  # 운영과 같은 스레드 수(BRIDGE_THREADS)
            t0 = time.monotonic()
            results = await asyncio.wait_for(
                asyncio.gather(*(asgi_post(main.app, path, p) for p in payloads)), timeout=60)
            return time.monotonic() - t0, results
    return asyncio.run(go())


def kpi5_bundle(i):
    """작은 번들: Deployment 1 + MaleWorkload 1 + PropagationPolicy 1."""
    b = etri_example_bundle()
    name = f"kpi5-{i:02d}"
    b["bundleId"] = f"t-{name}"
    b["missionId"] = f"t-{name}"
    m = b["workloadManifests"][0]["manifest"]
    m["metadata"]["name"] = name
    b["workloadManifests"] = [b["workloadManifests"][0]]
    b["maleBindings"][0]["targetRef"] = {"manifestId": b["workloadManifests"][0]["id"]}
    b["maleBindings"][0]["mcSpec"]["missionId"] = f"t-{name}"
    return b


@pytest.fixture
def fake(monkeypatch):
    f = SlowFakeK8s()
    monkeypatch.setattr(main, "k8s_client", f)
    return f


def test_32_apply_bundle_requests_are_not_serialized(fake):
    single, results = run_concurrently("/v1/apply-bundle", [kpi5_bundle(0)])
    assert results[0][0] == 200, results[0]
    assert single >= 2 * DELAY  # (Deployment + MaleWorkload) -> PropagationPolicy (단계 합침)

    fake.calls.clear()
    elapsed, results = run_concurrently("/v1/apply-bundle", [kpi5_bundle(i) for i in range(1, 33)])
    assert all(code == 200 and body["status"] == "SUCCESS" for code, body in results), results
    assert len(fake.calls) == 32 * 3
    # 직렬이면 32 x 0.3 s = 9.6 s. 단건 수준이어야 한다.
    assert elapsed < 3 * single, f"32 concurrent took {elapsed:.2f}s, single {single:.2f}s"


def test_32_render_bundle_requests_are_not_serialized(fake):
    single, _ = run_concurrently("/v1/render-bundle", [kpi5_bundle(0)])
    fake.calls.clear()
    elapsed, results = run_concurrently("/v1/render-bundle", [kpi5_bundle(i) for i in range(1, 33)])
    assert all(code == 200 and body["status"] == "RENDERED" for code, body in results), results
    assert all(c[2] for c in fake.calls)  # 전부 dry-run
    assert len(fake.calls) == 32 * 3
    # 예전: 요청 안에서 3건 직렬 + 요청끼리 직렬 = 9.6 s. 지금: 96건을 스레드 64개로 = 약 2 x 0.1 s.
    assert elapsed < 1.0, f"32 concurrent took {elapsed:.2f}s, single {single:.2f}s"


def _window(calls, kind):
    rows = [c for c in calls if c[0] == kind]
    return min(c[3] for c in rows), max(c[4] for c in rows), rows


def test_apply_bundle_keeps_level_order_and_parallelizes_within_level(fake):
    (code, body), = run_concurrently("/v1/apply-bundle", [patrol_robot_bundle()])[1]
    assert code == 200 and body["status"] == "SUCCESS", body

    cm_start, cm_end, _ = _window(fake.calls, "ConfigMap")
    dep_start, dep_end, deps = _window(fake.calls, "Deployment")
    mw_start, mw_end, mws = _window(fake.calls, "MaleWorkload")
    pp_start, _, pps = _window(fake.calls, "PropagationPolicy")
    # 단계 순서: ConfigMap -> (Deployment + MaleWorkload, 같은 단계) -> PropagationPolicy
    assert cm_end <= dep_start and cm_end <= mw_start
    assert dep_end <= pp_start and mw_end <= pp_start
    assert max(dep_start, mw_start) < min(dep_end, mw_end)  # 워크로드와 MaleWorkload 가 겹쳐 실행
    # 같은 단계 안은 동시에: 두 Deployment 의 호출 시간이 겹친다
    (_, _, _, s1, e1), (_, _, _, s2, e2) = deps
    assert max(s1, s2) < min(e1, e2)
    assert len(mws) == 2 and len(pps) == 2
    # 응답의 applied 는 적용 순서
    kinds = [a["kind"] for a in body["applied"]]
    assert kinds == ["ConfigMap", "Deployment", "Deployment", "MaleWorkload", "MaleWorkload",
                     "PropagationPolicy", "PropagationPolicy"]


def test_apply_bundle_stops_after_failed_level(fake):
    fake.fail = {("MaleWorkload", "slam-workload")}
    (code, body), = run_concurrently("/v1/apply-bundle", [patrol_robot_bundle()])[1]
    assert code == 500 and body["status"] == "PARTIAL_FAILURE", body
    assert body["failed"]["kind"] == "MaleWorkload" and body["failed"]["name"] == "slam-workload"
    assert {s["kind"] for s in body["skipped"]} == {"PropagationPolicy"}
    assert not any(c[0] == "PropagationPolicy" for c in fake.calls)
    applied = {(a["kind"], a["name"]) for a in body["applied"]}
    assert ("MaleWorkload", "object-detection-workload") in applied
    assert "alsoFailed" not in body


def test_legacy_apply_does_not_block_event_loop(monkeypatch):
    def slow_apply(resources):
        time.sleep(0.2)
        return [{"kind": r["kind"], "name": r["metadata"]["name"], "status": "success"} for r in resources]
    monkeypatch.setattr(main.sdi_client, "apply_resources", slow_apply)
    payloads = [{"mission": f"m{i}", "container_name": "c", "image": "busybox"} for i in range(16)]
    elapsed, results = run_concurrently("/v1/apply", payloads)
    assert all(code == 200 for code, _ in results), results
    assert elapsed < 1.6, f"16 concurrent legacy requests took {elapsed:.2f}s (serial = 3.2s)"


def test_apply_mw_separate_env_restores_old_order(fake, monkeypatch):
    # env 로 예전 4단계(Deployment -> MaleWorkload -> PP) 복원
    monkeypatch.setenv("SDI_APPLY_MW_SEPARATE", "on")
    (code, body), = run_concurrently("/v1/apply-bundle", [patrol_robot_bundle()])[1]
    assert code == 200, body
    _, dep_end, _ = _window(fake.calls, "Deployment")
    mw_start, mw_end, _ = _window(fake.calls, "MaleWorkload")
    pp_start, _, _ = _window(fake.calls, "PropagationPolicy")
    assert dep_end <= mw_start and mw_end <= pp_start


def test_apply_precheck_off_by_default(fake):
    (code, body), = run_concurrently("/v1/apply-bundle", [patrol_robot_bundle()])[1]
    assert code == 200 and "precheckMs" not in body
    assert not any(c[2] for c in fake.calls)


def test_apply_precheck_blocks_before_anything_is_applied(fake, monkeypatch):
    # 사전 dry-run 에서 틀리면 아무것도 적용하지 않음 (PARTIAL_FAILURE 대신 422)
    monkeypatch.setenv("BRIDGE_APPLY_PRECHECK", "on")
    fake.fail = {("MaleWorkload", "slam-workload")}
    (code, body), = run_concurrently("/v1/apply-bundle", [patrol_robot_bundle()])[1]
    assert code == 422 and body["status"] == "PRECHECK_FAILED", body
    assert body["applied"] == [] and isinstance(body["precheckMs"], float)
    assert [d for d in body["dryRun"] if d["status"] == "invalid"][0]["name"] == "slam-workload"
    assert fake.calls and all(c[2] for c in fake.calls)  # dry-run 호출만


def test_apply_precheck_passes_then_applies(fake, monkeypatch):
    monkeypatch.setenv("BRIDGE_APPLY_PRECHECK", "on")
    (code, body), = run_concurrently("/v1/apply-bundle", [patrol_robot_bundle()])[1]
    assert code == 200 and body["status"] == "SUCCESS" and body["precheckMs"] >= 0
    dry = [c for c in fake.calls if c[2]]
    real = [c for c in fake.calls if not c[2]]
    assert len(dry) == len(real) and max(c[4] for c in dry) <= min(c[3] for c in real)


def test_precheck_namespace_created_by_bundle_counts_as_valid():
    class Err(Exception):
        status = 404
        body = '{"message":"namespaces \\"sdi-new\\" not found"}'
    res = {"kind": "Deployment", "metadata": {"name": "a", "namespace": "sdi-new"}}
    assert main._ns_missing_only(res, Err(), {"sdi-new"})
    assert not main._ns_missing_only(res, Err(), set())  # 번들이 안 만드는 네임스페이스면 진짜 오류
    other = Err()
    other.body = '{"message":"the server could not find the requested resource"}'  # CRD 없음 등
    assert not main._ns_missing_only(res, other, {"sdi-new"})
