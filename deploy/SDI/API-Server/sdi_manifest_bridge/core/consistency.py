"""
번들 일관성 검사 · 워크로드 분류(출처 기록).

- bundle_warning_items(): 번들 안에서 서로 맞지 않는 값을 찾아 경고 항목({binding, code, message}) 목록으로 돌려준다.
  경고는 거부가 아니다(거부는 validate_bundle 몫). render/apply 응답의 warnings[] 와 MaleWorkload annotation 에 남긴다.
- classify(): 분류 축 C1 ~ C9 와 마감 D 를 채우고 값마다 출처(bundle / catalog / image / derived / default / missing)를
  적는다. 판정 순서 C1, C2, C3, C5, C4, C6, C7, C8, C9.
  기준 문서는 C1 · C2 · 마감이 없으면 변환 거부(REJECTED)지만, 번들 형식 합의 전이라 거부하지 않고 경고만 남긴다.
- 카탈로그는 호스트 클러스터 ConfigMap karmada-system/sdi-workload-catalog(catalog.yaml)를 읽는다.
  못 읽으면 카탈로그 없이 계산한다.
- fill_missing(): 명세에 빠진 항목 때문에 배치가 멈추지 않도록, 번들에 없는 mcSpec.rtDeadline · rtWcet 을
  카탈로그 → 예측표(karmada-system/sdi-predictions, predictions.yaml) → 기본값 순으로 채우고
  출처를 annotation sdi.keti.dev/filled 에 남긴다. 번들에 있는 값은 건드리지 않는다.
- 카탈로그 · 예측표 캐시를 요청 안에서 다시 읽지 않는다(_cached · start_cache_refresher, 아래 설명).
"""
import json
import logging
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import yaml

from .. import settings
from .models import IaCMaleBundle, MaleBinding

logger = logging.getLogger(__name__)

ANNO_WARNINGS = 'sdi.keti.dev/warnings'
ANNO_CLASS = 'sdi.keti.dev/classification'
ANNO_FILLED = 'sdi.keti.dev/filled'

# 이미지 이름으로 AI 추론(가속기 필요 가능성)을 짐작할 때 쓰는 단어
AI_IMAGE_HINTS = ('yolo', 'ultralytics', 'torch', 'tensorrt', 'onnx', 'cuda', 'triton', 'detector')
ACCEL_RESOURCE_HINTS = ('nvidia.com/gpu', 'amd.com/gpu', 'gpu', 'npu', 'deepx')

C5_ROLE = {
    'safety-function': 'safety', 'mission-core': 'core',
    'mission-assist': 'assist', 'assist': 'assist', 'aux': 'aux',
}

_catalog_cache: Dict[str, Any] = {'at': 0.0, 'data': None}

# ---------------------------------------------------------------------------
# 캐시
#   만료된 캐시를 요청 안에서 다시 읽으면(ConfigMap GET + YAML 해석) 그 요청이 그만큼 늦어진다.
#   그래서 한 번이라도 읽었으면 만료돼도 옛 값을 바로 돌려주고, 새로 읽기는 뒤 스레드 하나가 한다(같은 때 하나만).
#   처음(아직 못 읽음)만 요청 안에서 읽는다. main.py 시작 때 start_cache_refresher() 가
#   SDI_CATALOG_REFRESH_S(기본 15, 0 = 끔)초마다 뒤에서 새로 읽어 평소엔 만료되지 않는다.
#   YAML 은 C 로더(있으면) — 같은 결과, 몇 배 빠름.
#   못 읽으면(API 서버 순간 끊김 등) 옛 값을 그대로 둔다(처음이면 None = 카탈로그 없이 계산).
# ---------------------------------------------------------------------------

_YAML_LOADER = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
_refresh_lock = threading.Lock()
_refresher_started = False


def _yaml(text: str) -> Any:
    return yaml.load(text or '', Loader=_YAML_LOADER)


def _refresh(cache: Dict[str, Any], read: Callable[[], Any]) -> None:
    try:
        data = read()
        cache.update(at=time.time(), data=data)
    except Exception as e:  # 옛 값 유지, ttl 뒤 다시
        cache['at'] = time.time()
        logger.info(f"cache not refreshed, keep previous ({'none' if cache['data'] is None else 'stale'}): {e}")
    finally:
        cache['busy'] = False


def _cached(cache: Dict[str, Any], ttl: float, read: Callable[[], Any]) -> Any:
    if time.time() - cache['at'] < ttl:
        return cache['data']
    if not cache['at']:          # 아직 한 번도 못 읽음 → 요청 안에서
        _refresh(cache, read)
        return cache['data']
    with _refresh_lock:           # 만료 → 옛 값을 돌려주고 뒤에서 새로 읽음
        start = not cache.get('busy')
        cache['busy'] = True
    if start:
        threading.Thread(target=_refresh, args=(cache, read), daemon=True, name='sdi-cache-refresh').start()
    return cache['data']


def start_cache_refresher(interval: Optional[float] = None) -> bool:
    """카탈로그 · 예측표를 바로 한 번, 그 뒤 interval 초마다 뒤에서 새로 읽는다. 0 이면 안 띄움."""
    global _refresher_started
    if interval is None:
        interval = settings.catalog_refresh_s()
    with _refresh_lock:
        if interval <= 0 or _refresher_started:
            return False
        _refresher_started = True

    def loop():
        while True:
            _refresh(_catalog_cache, _read_catalog)
            _refresh(_pred_cache, _read_predictions)
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True, name='sdi-cache-refresher').start()
    logger.info(f"catalog / predictions refreshed in background every {interval:g}s")
    return True


def _read_configmap(ref: str, key: str, parse: Callable[[str], Any], what: str) -> Any:
    """못 읽으면 예외를 그대로 올린다(_refresh 가 옛 값 유지)."""
    from kubernetes import client as kclient
    from ..k8s.client import k8s_client
    ns, name = ref.split('/', 1)
    try:
        cm = kclient.CoreV1Api(k8s_client.host_api_client).read_namespaced_config_map(name, ns)
    except Exception as e:
        raise RuntimeError(f"{what} not loaded ({ref}): {e}") from e
    return parse((cm.data or {}).get(key, ''))


# ---------------------------------------------------------------------------
# 카탈로그
# ---------------------------------------------------------------------------

def _read_catalog() -> Optional[Dict[str, Any]]:
    return _read_configmap(settings.catalog_configmap(),
                           'catalog.yaml', parse_catalog, 'catalog')


def load_catalog(ttl: float = 30.0) -> Optional[Dict[str, Any]]:
    """카탈로그를 읽어 {이름: 항목} 으로 돌려준다. 30초 캐시(만료되면 옛 값 + 뒤에서 새로 읽음). 실패하면 None."""
    return _cached(_catalog_cache, ttl, _read_catalog)


_pred_cache: Dict[str, Any] = {'at': 0.0, 'data': None}


def _read_predictions() -> Optional[Dict[str, List[Dict[str, Any]]]]:
    return _read_configmap(settings.predictions_configmap(),
                           'predictions.yaml', parse_predictions, 'predictions')


def load_predictions(ttl: float = 30.0) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """예측표를 {작업 이름: [행...]} 으로 돌려준다. 30초 캐시(만료되면 옛 값 + 뒤에서 새로 읽음). 실패하면 None."""
    return _cached(_pred_cache, ttl, _read_predictions)


def parse_predictions(text: str) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    doc = _yaml(text) or {}
    out: Dict[str, List[Dict[str, Any]]] = {}
    for p in doc.get('predictions') or []:
        if isinstance(p, dict) and p.get('workload'):
            out.setdefault(p['workload'], []).append(p)
    return out or None


def _max_num(vals: List[Any]) -> Optional[float]:
    nums = [float(v) for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0]
    return max(nums) if nums else None


def fill_missing(name: str, mc_spec: Dict[str, Any], entry: Optional[Dict[str, Any]],
                 predictions: Optional[Dict[str, List[Dict[str, Any]]]]) -> Dict[str, Dict[str, Any]]:
    """빈 rtDeadline · rtWcet 을 카탈로그 → 예측표 → 기본값 순으로 채운다. 채운 것만 {칸: {value, source}}.

    rtDeadline: 카탈로그 deadlineMs → (예측표에는 마감 없음) → 기본값 rtPeriod(주기 = 마감)
    rtWcet:     등급별 카탈로그 expectedExecMs(그 등급 실측 cHiMs 가 있으면 실측) 최댓값 → 카탈로그 없으면 예측표 cHiMs 최댓값 → 비워 둠
    """
    filled: Dict[str, Dict[str, Any]] = {}
    rows = (predictions or {}).get(name) or (predictions or {}).get(re.sub(r'-workload$', '', name)) or []

    if mc_spec.get('rtDeadline') is None:
        v = _max_num([(entry or {}).get('deadlineMs')])
        if v is not None:
            filled['rtDeadline'] = _val(int(round(v)), 'catalog')
        elif mc_spec.get('rtPeriod'):
            filled['rtDeadline'] = _val(int(mc_spec['rtPeriod']), 'default-period')

    if mc_spec.get('rtWcet') is None:
        # HW 등급마다 카탈로그 expectedExecMs 를 쓰되, 그 등급에 예측표 실측(source: measured) cHiMs 가
        # 있으면 실측값으로 바꾼 뒤 등급 중 최댓값(배치 전이라 어느 등급에 놓일지 모르므로 최악 기준). 실측 없는 등급은
        # 카탈로그 그대로라 덜 잡지 않음. 실측 아닌 예측표 행(카탈로그 x1.5 사본)은 카탈로그가 비었을 때만 씀
        per: Dict[str, Any] = {}
        for hw, h in ((entry or {}).get('byHwClass') or {}).items():
            v = _max_num([h.get('expectedExecMs')]) if isinstance(h, dict) else None
            if v is not None:
                per[hw] = (v, 'catalog')
        if per:
            for r in rows:
                v = _max_num([r.get('cHiMs')])
                if v is not None and r.get('source') == 'measured' and r.get('hwClass') in per:
                    per[r['hwClass']] = (v, 'predictions-measured')
            v, src = max(per.values(), key=lambda x: x[0])
            filled['rtWcet'] = _val(int(-(-v // 1)), src)
        else:
            v = _max_num([r.get('cHiMs') for r in rows])
            if v is not None:
                filled['rtWcet'] = _val(int(-(-v // 1)), 'predictions')

    for k, fv in filled.items():
        mc_spec[k] = fv['value']
    return filled


def parse_catalog(text: str) -> Optional[Dict[str, Any]]:
    doc = _yaml(text) or {}
    out = {}
    for w in doc.get('workloads') or []:
        if isinstance(w, dict) and w.get('name'):
            out[w['name']] = w
    if out and isinstance(doc.get('safetyFunctions'), list):
        out['__safetyFunctions__'] = doc['safetyFunctions']   # C5 안전 기능 목록. 작업 이름과 겹치지 않는 키
    return out or None


def _catalog_entry(catalog: Optional[Dict[str, Any]], manifest_name: str) -> Optional[Dict[str, Any]]:
    if not catalog:
        return None
    return catalog.get(manifest_name) or catalog.get(re.sub(r'-workload$', '', manifest_name))


def _catalog_needs_accel(entry: Optional[Dict[str, Any]]) -> Optional[str]:
    """카탈로그가 가속기를 요구하면 그 이름(gpu/npu 등)을, 아니면 None."""
    if not entry:
        return None
    for key in ('accelerator', 'accel', 'requiresAccel', 'requires'):
        v = entry.get(key)
        if isinstance(v, str) and v.lower() not in ('', 'none', 'cpu', 'false'):
            return v
        if isinstance(v, (list, tuple)) and v:
            return ','.join(str(x) for x in v)
        if v is True:
            return 'accelerator'
    by_hw = [v for v in (entry.get('byHwClass') or {}).values() if isinstance(v, dict)]
    accels = [str(v.get('accel', 'none')).lower() for v in by_hw]
    # 모든 HW 등급에서 가속기가 필요할 때만 "필수"로 본다
    if accels and all(a not in ('none', 'cpu', '') for a in accels):
        return ','.join(sorted(set(accels)))
    return None


# ---------------------------------------------------------------------------
# 매니페스트에서 값 꺼내기
# ---------------------------------------------------------------------------

def _pod_spec(manifest: Dict[str, Any]) -> Dict[str, Any]:
    spec = manifest.get('spec') or {}
    if manifest.get('kind') == 'Pod':
        return spec
    return ((spec.get('template') or {}).get('spec')) or {}


def _cpu_cores(q: Any) -> Optional[float]:
    if q is None:
        return None
    s = str(q).strip()
    try:
        return float(s[:-1]) / 1000.0 if s.endswith('m') else float(s)
    except ValueError:
        return None


def _containers(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(_pod_spec(manifest).get('containers') or [])


def _cpu_limit(manifest: Dict[str, Any]) -> Optional[float]:
    total, seen = 0.0, False
    for c in _containers(manifest):
        v = _cpu_cores(((c.get('resources') or {}).get('limits') or {}).get('cpu'))
        if v is not None:
            total, seen = total + v, True
    return total if seen else None


def _accel_requested(manifest: Dict[str, Any], hints=ACCEL_RESOURCE_HINTS) -> bool:
    for c in _containers(manifest):
        res = c.get('resources') or {}
        for part in ('limits', 'requests'):
            for k in (res.get(part) or {}):
                if any(h in k.lower() for h in hints):
                    return True
    return False


def _gpu_requested(manifest: Dict[str, Any]) -> bool:
    """GPU 자원만(NPU sdi.keti.dev/npu 는 runtimeClass 가 필요 없음)."""
    return _accel_requested(manifest, ('gpu',))


def _gpu_by_runtime(manifest: Dict[str, Any]) -> bool:
    """자원 요청 없이 GPU 를 쓰는 형태: runtimeClassName nvidia 이거나 NVIDIA_VISIBLE_DEVICES 가 비어 있지 않음."""
    if 'nvidia' in str(_pod_spec(manifest).get('runtimeClassName') or '').lower():
        return True
    return any(e.get('name') == 'NVIDIA_VISIBLE_DEVICES' and str(e.get('value', '')).lower() not in ('', 'none', 'void')
               for c in _containers(manifest) for e in c.get('env') or [])


def _images(manifest: Dict[str, Any]) -> List[str]:
    return [str(c.get('image', '')) for c in _containers(manifest)]


def _image_looks_ai(manifest: Dict[str, Any]) -> bool:
    return any(h in img.lower() for img in _images(manifest) for h in AI_IMAGE_HINTS)


# ---------------------------------------------------------------------------
# 워크로드 분류
# ---------------------------------------------------------------------------

def _val(value: Any, source: str) -> Dict[str, Any]:
    return {'value': value, 'source': source}


def _catalog_hw(e: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {k: v for k, v in ((e or {}).get('byHwClass') or {}).items() if isinstance(v, dict)}


def _classify_accel(binding: MaleBinding, target: Dict[str, Any], e: Optional[Dict[str, Any]],
                    c2: Optional[str], c6: Optional[str], d: Optional[float]) -> Dict[str, Any]:
    """C7 가속기 의존. 카탈로그에 컴파일 산출물 목록이 없어 byHwClass 의 accel=npu 를 NPU 산출물로 본다."""
    if c2 == 'training' and c6 != 'device':
        return _val('gpu', 'derived')
    if _accel_requested(target):
        return _val('gpu', 'bundle-resource')   # 매니페스트가 GPU · NPU 자원을 직접 요청
    hw = _catalog_hw(e)
    accels = {str(v.get('accel') or 'none').lower() for v in hw.values()}
    if 'npu' in accels:
        cpu = [v.get('expectedExecMs') for v in hw.values()
               if str(v.get('accel') or 'none').lower() in ('none', 'cpu') and v.get('expectedExecMs') is not None]
        if not cpu or d is None:
            return _val('npuPreferred', 'default')   # WARN_ACCEL_DEFAULT
        return _val('npuRequired' if min(cpu) > d else 'npuPreferred', 'catalog')
    if 'gpu' in accels and _catalog_needs_accel(e):
        return _val('gpu', 'catalog')
    return _val('cpu', 'catalog' if hw else 'default')


def classify(bundle: IaCMaleBundle, binding: MaleBinding, target: Dict[str, Any],
             catalog: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    name = (target.get('metadata') or {}).get('name', '')
    e = _catalog_entry(catalog, name)
    mc = binding.mcSpec
    b = binding
    out: Dict[str, Any] = {'catalog': (e or {}).get('name')}

    # C1 미션 계열 — 번들 → 카탈로그. 다른 값으로 유도하지 않음(장애물 감지처럼 추론이지만 구동 계열인 작업이 있음)
    if b.missionKind:
        out['C1'] = _val(b.missionKind, 'bundle')
    elif e and e.get('missionKind'):
        out['C1'] = _val(e['missionKind'], 'catalog')
    else:
        out['C1'] = _val(None, 'missing')        # 기준 문서: REJECTED MISSING_MISSION_KIND

    # C2 처리 형태
    if b.kind:
        out['C2'] = _val(b.kind, 'bundle')
    elif e and e.get('kind'):
        out['C2'] = _val(e['kind'], 'catalog')
    elif b.rounds:
        out['C2'] = _val('training', 'derived')
    elif _image_looks_ai(target):
        out['C2'] = _val('inference', 'image')
    else:
        out['C2'] = _val(None, 'unknown')
    c2 = out['C2']['value']

    # C3 실행 형태: 주기 → 배치(rounds) → 이벤트(trigger) → 상시
    if mc and mc.rtPeriodMs:
        out['C3'] = _val('periodic', 'bundle')
    elif b.rounds:
        out['C3'] = _val('batch', 'bundle')
    elif b.trigger:
        out['C3'] = _val('event', 'bundle')
    elif e and e.get('c3'):
        out['C3'] = _val(e['c3'], 'catalog')
    else:
        out['C3'] = _val('continuous', 'default')
    c3 = out['C3']['value']

    # 마감 D (상시형은 응답 시한이 없으면 1 s)
    if mc and mc.rtDeadlineMs:
        out['D'] = _val(mc.rtDeadlineMs, 'bundle')
    elif e and e.get('deadlineMs'):
        out['D'] = _val(e['deadlineMs'], 'catalog')
    elif mc and mc.rtPeriodMs:
        out['D'] = _val(mc.rtPeriodMs, 'bundle-period')
    elif c3 == 'continuous':
        out['D'] = _val(1000, 'default')
    else:
        out['D'] = _val(None, 'unknown')
    d = out['D']['value']

    # C5 안전 관련성: 번들 safety · usage → 카탈로그(c5 · safetyFunction 목록) → 번들 role → C2 로 유도
    safety_fns = set((catalog or {}).get('__safetyFunctions__') or [])
    if b.safety is True or b.usage == 'driving-perception':
        out['C5'] = _val('safety', 'bundle')
    elif e and e.get('c5'):
        out['C5'] = _val(C5_ROLE.get(e['c5'], e['c5']), 'catalog')
    elif e and e.get('safetyFunction') and (not safety_fns or e['safetyFunction'] in safety_fns):
        out['C5'] = _val('safety', 'catalog')
    elif b.role in ('core', 'support', 'aux'):
        out['C5'] = _val({'support': 'assist'}.get(b.role, b.role), 'bundle')
    elif c2 in ('training', 'deploy'):
        out['C5'] = _val('assist', 'derived')
    elif c2 == 'service':
        out['C5'] = _val('aux', 'derived')
    else:
        out['C5'] = _val(None, 'unknown')
    c5 = out['C5']['value']

    # C4 마감 엄격도: 명시값 → 카탈로그 → C5 · C3 로 유도
    if b.strictness:
        out['C4'] = _val(b.strictness.lower(), 'bundle')
    elif e and e.get('c4'):
        out['C4'] = _val(str(e['c4']).lower(), 'catalog')
    elif c5 is not None:
        out['C4'] = _val('hard' if c5 == 'safety' else 'firm' if (c5 == 'core' and c3 == 'periodic') else 'soft',
                         'derived')
    else:
        out['C4'] = _val(None, 'unknown')

    # C6 실행 위치: 번들 placement · 기체 지정 → 카탈로그 → 엣지 가능
    if b.placement:
        out['C6'] = _val(b.placement, 'bundle')
    elif b.targetDevice:
        out['C6'] = _val('device', 'bundle-targetDevice')
    elif e and e.get('placementHint'):
        out['C6'] = _val(e['placementHint'], 'catalog')
    elif e and set(e.get('io') or []) & {'sensor', 'actuator'}:
        out['C6'] = _val('device', 'catalog')
    else:
        out['C6'] = _val('any', 'default')

    # C7 가속기 의존
    out['C7'] = _classify_accel(b, target, e, c2, out['C6']['value'], d)

    # C8 분할 가능성
    if b.splitConfigs:
        out['C8'] = _val('splitInfer' if c2 == 'inference' else 'splitTrain', 'bundle')
    else:
        out['C8'] = _val('none', 'default')

    # C9 상태 유지: 번들 checkpoint · stateful → 카탈로그 → 무상태(추론 · 제어 또는 볼륨 없음)
    ck = b.checkpoint or {}
    if ck.get('supported') is True:
        out['C9'] = _val('ckpt', 'bundle')
    elif b.stateful is True:
        out['C9'] = _val('noCkpt', 'bundle')
    elif e and e.get('state'):
        out['C9'] = _val(e['state'], 'catalog')
    elif c2 in ('inference', 'control') or not _pod_spec(target).get('volumes'):
        out['C9'] = _val('stateless', 'default')
    else:
        out['C9'] = _val(None, 'unknown')

    if e and e.get('chain'):
        out['chain'] = _val(e['chain'], 'catalog')
    return out


# ---------------------------------------------------------------------------
# 일관성 검사
# ---------------------------------------------------------------------------

def _w(label: str, code: str, msg: str) -> Dict[str, str]:
    return {'binding': label, 'code': code, 'message': msg}


def binding_warnings(label: str, binding: MaleBinding, target: Dict[str, Any],
                     cls: Dict[str, Any], catalog_entry: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    mc = binding.mcSpec
    period = mc.rtPeriodMs if mc else None
    wcet = mc.rtWcetMs if mc else None
    deadline = cls.get('D', {}).get('value')

    # ① WCET ÷ 주기 > CPU 한도
    lim = _cpu_limit(target)
    if wcet and period and lim is not None:
        need = wcet / period
        if need > lim + 1e-9:
            out.append(_w(label, 'CPU_LIMIT_BELOW_UTIL',
                          f"rtWcetMs/rtPeriodMs = {wcet}/{period} = {need:.2f} cores > cpu limit {lim:.2f}"))
    # ② WCET 가 마감 · 주기보다 김
    if wcet and deadline and wcet > deadline:
        out.append(_w(label, 'WCET_OVER_DEADLINE', f"rtWcetMs {wcet} > deadline {deadline}ms"))
    if wcet and period and wcet > period:
        out.append(_w(label, 'WCET_OVER_PERIOD', f"rtWcetMs {wcet} > rtPeriodMs {period}"))
    # ③ HC 요청인데 마감 없음
    if mc and mc.criticality == 'C' and not deadline:
        out.append(_w(label, 'HC_NO_DEADLINE', "criticality C(HC) but no deadline in bundle or catalog"))
    # ④ 가속기가 필요한데 요청 없음(CPU 로 실행돼 마감을 놓침)
    need_accel = _catalog_needs_accel(catalog_entry)
    why = f"catalog requires {need_accel}" if need_accel else None
    if not why and cls.get('C2', {}).get('value') == 'inference' and _image_looks_ai(target):
        why = "AI inference image"
    if why and not _accel_requested(target):
        if _gpu_by_runtime(target):
            # runtimeClass nvidia + NVIDIA_VISIBLE_DEVICES 로 GPU 를 쓰지만 자원 요청이 없음
            out.append(_w(label, 'GPU_NOT_ACCOUNTED',
                          f"{why} uses GPU via runtimeClass/NVIDIA_VISIBLE_DEVICES but requests no nvidia.com/gpu "
                          "(scheduler cannot count GPU use)"))
        else:
            out.append(_w(label, 'ACCEL_NOT_REQUESTED',
                          f"{why} but no GPU/NPU resource requested (runs on CPU, deadline likely missed)"))
    # ⑤ GPU 요청인데 runtimeClassName 없음(NVIDIA 런타임이 기본이 아닌 엣지는 runtimeClassName: nvidia 필요)
    if _gpu_requested(target) and not _pod_spec(target).get('runtimeClassName'):
        out.append(_w(label, 'GPU_NO_RUNTIMECLASS',
                      "GPU requested but runtimeClassName not set (GPU edge nodes need runtimeClassName: nvidia)"))
    # ⑥ 역할(C5)을 모름 → 등급 규칙 R01 · R05 · M 을 못 씀
    if cls.get('C5', {}).get('value') is None:
        out.append(_w(label, 'ROLE_UNKNOWN', "role(C5) not found in catalog; grade uses M=1, no safety gate"))
    # ⑦ 누락 처리. 기준 문서는 C1 누락이면 거부지만 형식 합의 전이라 경고만
    if cls.get('C1', {}).get('value') is None:
        out.append(_w(label, 'MISSING_MISSION_KIND', "missionKind(C1) not in bundle or catalog (v2.0: REJECTED)"))
    if cls.get('C5', {}).get('value') == 'safety' and cls['C5'].get('source') == 'catalog' and binding.safety is None:
        out.append(_w(label, 'WARN_SAFETY_FROM_CATALOG', "safety not marked in bundle; safety function taken from catalog"))
    # 번들 safety=false 가 annotation 으로 Operator 에 가서 카탈로그 안전 기능(R01 → HC)을 이긴다
    if cls.get('C5', {}).get('value') == 'safety' and cls['C5'].get('source') == 'catalog' and binding.safety is False:
        out.append(_w(label, 'SAFETY_BUNDLE_OVERRIDES_CATALOG',
                      "bundle safety=false overrides catalog safety function (grade rule R01 not applied)"))
    if cls.get('C7', {}).get('source') == 'default' and cls['C7'].get('value') != 'cpu':
        out.append(_w(label, 'WARN_ACCEL_DEFAULT', "accelerator dependency(C7) defaulted: no CPU execution time to compare"))
    return out


def analyze_bundle(bundle: IaCMaleBundle, catalog: Optional[Dict[str, Any]] = None
                   ) -> Dict[str, Dict[str, Any]]:
    """바인딩마다 {name, namespace, classification, warnings} 를 돌려준다. key = MaleWorkload 이름."""
    manifests = {wm.id: wm.manifest for wm in bundle.workloadManifests}
    result: Dict[str, Dict[str, Any]] = {}
    for i, b in enumerate(bundle.maleBindings):
        target = manifests.get(b.targetRef.manifestId)
        if target is None:
            continue
        meta = target.get('metadata') or {}
        name = meta.get('name', '')
        label = b.id or f"maleBindings[{i}]"
        cls = classify(bundle, b, target, catalog)
        result[f"{name}-workload"] = {
            'name': name,
            'namespace': meta.get('namespace', 'default'),
            'classification': cls,
            'warnings': binding_warnings(label, b, target, cls, _catalog_entry(catalog, name)),
        }
    return result


def bundle_warning_items(bundle: IaCMaleBundle, catalog: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    """모든 바인딩의 경고 항목({binding, code, message})을 한 목록으로. 문자열 목록은 validate.bundle_warnings."""
    return [w for a in analyze_bundle(bundle, catalog).values() for w in a['warnings']]


def annotate_resources(bundle: IaCMaleBundle, resources: List[Dict[str, Any]],
                       catalog: Optional[Dict[str, Any]] = None,
                       predictions: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> List[Dict[str, str]]:
    """MaleWorkload 에 분류 · 경고 annotation 을 붙이고 경고 목록을 돌려준다(main.py 에서 호출).
    빈 rtDeadline · rtWcet 은 fill_missing 으로 채운다."""
    if catalog is None:
        catalog = load_catalog()
    if predictions is None:
        predictions = load_predictions()
    info = analyze_bundle(bundle, catalog)
    for r in resources:
        if r.get('kind') != 'MaleWorkload':
            continue
        a = info.get((r.get('metadata') or {}).get('name', ''))
        if not a:
            continue
        ann = r['metadata'].setdefault('annotations', {})
        mc_spec = r.setdefault('spec', {}).setdefault('mcSpec', {})
        filled = json.loads(ann.get(ANNO_FILLED, '{}'))  # 번들 latencyBudget 로 채운 것(convert.py)
        filled.update(fill_missing(a['name'], mc_spec, _catalog_entry(catalog, a['name']), predictions))
        if filled:
            ann[ANNO_FILLED] = json.dumps(filled, ensure_ascii=False, sort_keys=True)
        ann[ANNO_CLASS] = json.dumps(a['classification'], ensure_ascii=False, sort_keys=True)
        if a['warnings']:
            ann[ANNO_WARNINGS] = json.dumps(a['warnings'], ensure_ascii=False)
    warnings = [w for a in info.values() for w in a['warnings']]
    for w in warnings:
        logger.warning(f"bundle '{bundle.bundleId}' {w['binding']}: {w['code']} {w['message']}")
    return warnings


def warning_strings(ws: List[Dict[str, str]]) -> List[str]:
    """기존 응답 warnings(문자열 목록) 형식으로 바꾼다."""
    return [f"maleBinding '{w['binding']}': {w['code']} {w['message']}" for w in ws]
