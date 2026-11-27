"""
번들 정리 · 검증 · 경고.

- normalize_bundle(): 협의 규격 칸을 내부 칸으로 옮긴 사본을 만든다(검증 · 변환 앞에서 한 번, 여러 번 불러도 결과 같음).
- validate_bundle(): all-or-nothing 검증. 오류가 하나라도 있으면 번들 전체를 거부한다.
- bundle_warnings(): 거부 사유는 아니지만 응답에 함께 실어 주는 경고 문자열 목록.
"""
from typing import Any, Dict, List, Optional

from .. import settings
from .models import IaCMaleBundle, Importance, MCSpec, MaleTargets

# importance(accuracy+latency+energy) 합 = 1 검증 허용 오차
IMPORTANCE_SUM_TOLERANCE = 0.01

# IaC 알고리즘 지정: 스케줄러 normalizeAlgorithm 과 같은 이름. MaleWorkload annotation 으로 넘김
SCHEDULING_ALGORITHMS = {
    'intent': 'intent-driven', 'intent-driven': 'intent-driven',
    'swarm': 'collaborative-swarm', 'collaborative-swarm': 'collaborative-swarm',
    'predictive': 'predictive-context', 'predictive-context': 'predictive-context',
}

# missionType 별 기본 ALE 가중치(MALE 논문 Section IV). importance 를 직접 주면 그 값이 우선
MISSION_TYPE_IMPORTANCE = {
    'autonomous-vehicle': {'accuracy': 0.6, 'latency': 0.3, 'energy': 0.1},
    'realtime-robotics': {'accuracy': 0.1, 'latency': 0.7, 'energy': 0.2},
    'iot-sensing': {'accuracy': 0.2, 'latency': 0.1, 'energy': 0.7},
}
DEFAULT_IMPORTANCE = {'accuracy': 0.34, 'latency': 0.33, 'energy': 0.33}   # importance · missionType 둘 다 없을 때
MISSION_ATOMICITY = ('gang', 'criticalOnly', 'bestEffort')
# placement: 협의 규격(deviceLocked · flexible) → 내부 값(device · any). 예전 값(device · any · edge · cloud)도 그대로 받음
PLACEMENT_ALIASES = {'devicelocked': 'device', 'flexible': 'any'}
PLACEMENT_VALUES = ('device', 'any', 'edge', 'cloud')


# ---------------------------------------------------------------------------
# 협의 규격 → 내부 형식 (검증 · 변환 앞에서 한 번. 여러 번 불러도 결과 같음)
# ---------------------------------------------------------------------------

def normalize_bundle(bundle: IaCMaleBundle):
    """협의 규격 칸을 내부 칸으로 옮긴 사본, 오류 목록, 경고 목록을 돌려준다.

    criticality → mcSpec.criticality, rtSpec → mcSpec.rtPeriodMs · rtDeadlineMs,
    missionRequirements → maleTargets, placement deviceLocked/flexible → device/any.
    importance 가 없으면 missionType 기본값 → 같은 비중, criticality 가 없으면 A(바닥값 없음, Operator 규칙으로 등급).
    같은 값을 예전 칸과 새 칸에 다르게 주면 오류.
    """
    errors: List[str] = []
    warnings: List[str] = []
    n = bundle.model_copy(deep=True)
    mtype = (n.missionType or '').strip() or None
    if mtype and mtype not in MISSION_TYPE_IMPORTANCE:
        # 생성기는 범용이라 유형이 늘 수 있음(예: LLM 학습) → 거부하지 않고 받음. 기본 가중치만 못 고르므로
        # importance 가 없는 바인딩은 같은 비중(아래에서 경고). missionType 값은 annotation 에 그대로 기록.
        # 모든 바인딩이 importance 를 직접 주면 기본 가중치를 안 쓰므로 경고하지 않음
        if any(b.importance is None for b in n.maleBindings):
            warnings.append(f"missionType '{mtype}' has no default importance (known: {sorted(MISSION_TYPE_IMPORTANCE)}); "
                            f"bindings without importance use equal weights")
        mtype = None
    if n.missionAtomicity and n.missionAtomicity not in MISSION_ATOMICITY:
        errors.append(f"missionAtomicity '{n.missionAtomicity}' must be one of {list(MISSION_ATOMICITY)}")
    for i, b in enumerate(n.maleBindings):
        label = b.id or f"maleBindings[{i}]"
        fill = dict(b.normalizedFill)
        mc = (b.mcSpec or MCSpec()).model_copy()
        # criticality
        if b.criticality is not None and b.criticality not in ('A', 'B', 'C'):
            errors.append(f"maleBinding '{label}': criticality must be one of A/B/C (C is the highest), got '{b.criticality}'")
        elif b.criticality and mc.criticality and mc.criticality != b.criticality and fill.get('criticality') is None:
            errors.append(f"maleBinding '{label}': criticality '{b.criticality}' conflicts with mcSpec.criticality '{mc.criticality}'")
        elif b.criticality:
            mc.criticality = b.criticality
        declared_crit = bool(mc.criticality) and fill.get('criticality') is None
        if not mc.criticality:
            mc.criticality = 'A'
            fill['criticality'] = {'value': 'A', 'source': 'default-lowest'}
            warnings.append(f"maleBinding '{label}': criticality not given → A (no protection floor; operator rules decide the grade)")
        if n.missionAtomicity == 'criticalOnly' and not declared_crit:
            errors.append(f"maleBinding '{label}': missionAtomicity criticalOnly needs criticality on every binding")
        # rtSpec
        if b.rtSpec:
            for src, dst in (('periodMs', 'rtPeriodMs'), ('deadlineMs', 'rtDeadlineMs')):
                v = getattr(b.rtSpec, src)
                if v is None:
                    continue
                cur = getattr(mc, dst)
                if cur is not None and cur != v:
                    errors.append(f"maleBinding '{label}': rtSpec.{src} ({v}) conflicts with mcSpec.{dst} ({cur})")
                else:
                    setattr(mc, dst, v)
        b.mcSpec = mc
        # missionRequirements → maleTargets
        if b.missionRequirements:
            t = (b.maleTargets or MaleTargets()).model_copy()
            for k, v in b.missionRequirements.model_dump(exclude_none=True).items():
                cur = getattr(t, k)
                if cur is not None and cur != v:
                    errors.append(f"maleBinding '{label}': missionRequirements.{k} ({v}) conflicts with maleTargets.{k} ({cur})")
                else:
                    setattr(t, k, v)
            b.maleTargets = t
        # placement
        if b.placement:
            p = PLACEMENT_ALIASES.get(b.placement.strip().lower(), b.placement.strip().lower())
            if p not in PLACEMENT_VALUES:
                errors.append(f"maleBinding '{label}': placement '{b.placement}' must be deviceLocked or flexible")
            else:
                b.placement = p
        # C 는 디바이스 안 실행이 정해진 서브미션(deviceLocked)에만 그대로 적용, 그 밖은 Operator 가 B 로 대우(R08) → 미리 알림
        if mc.criticality == 'C' and b.placement != 'device':
            warnings.append(f"maleBinding '{label}': criticality C applies only to placement deviceLocked; "
                            f"this binding is treated as B")
        # importance
        if b.importance is None:
            if mtype:
                b.importance = Importance(**MISSION_TYPE_IMPORTANCE[mtype])
                fill['importance'] = {'value': MISSION_TYPE_IMPORTANCE[mtype], 'source': f'missionType:{mtype}'}
            else:
                b.importance = Importance(**DEFAULT_IMPORTANCE)
                fill['importance'] = {'value': DEFAULT_IMPORTANCE, 'source': 'default-equal'}
                warnings.append(f"maleBinding '{label}': importance and missionType not given → equal weights")
        b.normalizedFill = fill
    return n, errors, warnings


# ---------------------------------------------------------------------------
# 검증 (all-or-nothing: 에러가 하나라도 있으면 번들 전체 거부)
# ---------------------------------------------------------------------------

def _algorithm(name: Optional[str]) -> Optional[str]:
    return SCHEDULING_ALGORITHMS.get(str(name or '').strip().lower().replace('_', '-'))


def validate_bundle(bundle: IaCMaleBundle) -> List[str]:
    """번들의 정합성을 검사하고 에러 메시지 목록을 반환한다 (빈 목록 = 통과)."""
    bundle, norm_errors, _ = normalize_bundle(bundle)   # 협의 규격 칸을 내부 칸으로
    errors: List[str] = list(norm_errors)

    manifests_by_id: Dict[str, Dict[str, Any]] = {}
    for wm in bundle.workloadManifests:
        if wm.id in manifests_by_id:
            errors.append(f"duplicate workloadManifest id: '{wm.id}'")
            continue
        m = wm.manifest
        if not m.get('apiVersion') or not m.get('kind') or not (m.get('metadata') or {}).get('name'):
            errors.append(
                f"workloadManifest '{wm.id}': manifest must contain apiVersion, kind, metadata.name")
            continue
        manifests_by_id[wm.id] = m

    seen_binding_ids = set()
    if bundle.schedulingAlgorithm and _algorithm(bundle.schedulingAlgorithm) is None:
        errors.append(f"schedulingAlgorithm '{bundle.schedulingAlgorithm}' must be one of {sorted(set(SCHEDULING_ALGORITHMS.values()))}")
    for i, b in enumerate(bundle.maleBindings):
        label = b.id or f"maleBindings[{i}]"
        if b.schedulingAlgorithm and _algorithm(b.schedulingAlgorithm) is None:
            errors.append(f"maleBinding '{label}': schedulingAlgorithm '{b.schedulingAlgorithm}' must be one of "
                          f"{sorted(set(SCHEDULING_ALGORITHMS.values()))}")
        if b.id:
            if b.id in seen_binding_ids:
                errors.append(f"duplicate maleBinding id: '{b.id}'")
            seen_binding_ids.add(b.id)

        target = manifests_by_id.get(b.targetRef.manifestId)
        if target is None:
            errors.append(
                f"maleBinding '{label}': targetRef.manifestId "
                f"'{b.targetRef.manifestId}' not found in workloadManifests")
            continue

        meta = target.get('metadata') or {}
        checks = [
            ('apiVersion', b.targetRef.apiVersion, target.get('apiVersion')),
            ('kind', b.targetRef.kind, target.get('kind')),
            ('name', b.targetRef.name, meta.get('name')),
            ('namespace', b.targetRef.namespace, meta.get('namespace')),
        ]
        for field, expected, actual in checks:
            if expected is not None and expected != actual:
                errors.append(
                    f"maleBinding '{label}': targetRef.{field} '{expected}' does not match "
                    f"manifest '{b.targetRef.manifestId}' ({field}='{actual}')")

        # ALE 가중치는 합이 1이어야 점수 비교가 성립 (허용 오차 ±0.01)
        imp = b.importance
        total = imp.accuracy + imp.latency + imp.energy
        if abs(total - 1.0) > IMPORTANCE_SUM_TOLERANCE:
            errors.append(
                f"maleBinding '{label}': importance values must sum to 1 (±{IMPORTANCE_SUM_TOLERANCE}), "
                f"got {total:.3f}")

        # 혼합중요도 등급은 미션 소유자 선언값. ALE 축과 독립이며 플랫폼이 추론하지 않으므로 필수.
        mc = b.mcSpec
        if not mc or not mc.criticality:
            errors.append(
                f"maleBinding '{label}': mcSpec.criticality is required (A/B/C, C is the highest)")
        if mc:
            if mc.criticality and mc.criticality not in ('A', 'B', 'C'):
                errors.append(
                    f"maleBinding '{label}': mcSpec.criticality must be one of A/B/C, "
                    f"got '{mc.criticality}'")

            # mcSpec.missionId는 하위호환용. 번들 최상위 missionId와 다르면 거부
            if mc.missionId and bundle.missionId and mc.missionId != bundle.missionId:
                errors.append(
                    f"maleBinding '{label}': mcSpec.missionId '{mc.missionId}' does not match "
                    f"bundle missionId '{bundle.missionId}'")

            # RT 값은 지정 시 양수
            for field in ('rtPeriodMs', 'rtWcetMs', 'rtDeadlineMs'):
                value = getattr(mc, field)
                if value is not None and value <= 0:
                    errors.append(f"maleBinding '{label}': mcSpec.{field} must be positive, got {value}")

            # WCET > deadline 이면 어떤 스케줄러도 마감을 지킬 수 없음
            if (mc.rtWcetMs is not None and mc.rtDeadlineMs is not None
                    and mc.rtWcetMs > mc.rtDeadlineMs):
                errors.append(
                    f"maleBinding '{label}': mcSpec.rtWcetMs ({mc.rtWcetMs}) must not exceed "
                    f"mcSpec.rtDeadlineMs ({mc.rtDeadlineMs})")
            # deadline <= period(constrained deadline)는 정상. 거부하지 않는다.
            # deadline > period(arbitrary deadline)는 bundle_warnings()에서 경고만.

    return errors


def bundle_warnings(bundle: IaCMaleBundle, check_devices: bool = False) -> List[str]:
    """거부 사유는 아니지만 응답에 함께 실어 주는 경고 문자열 목록.
    check_devices: render 에서만 True(장치 이름 확인 = 히트맵 조회, apply 지연에 안 넣음)."""
    bundle, _, warnings = normalize_bundle(bundle)      # 기본값으로 채운 칸 경고 포함
    warnings = list(warnings)
    for i, b in enumerate(bundle.maleBindings):
        label = b.id or f"maleBindings[{i}]"
        mc = b.mcSpec
        if (mc and mc.rtDeadlineMs is not None and mc.rtPeriodMs is not None
                and mc.rtDeadlineMs > mc.rtPeriodMs):
            warnings.append(
                f"maleBinding '{label}': rtDeadlineMs ({mc.rtDeadlineMs}) > rtPeriodMs ({mc.rtPeriodMs}); "
                f"treated as arbitrary deadline")
        # 지금 없는 장치 이름은 render 에서 알려 줌. 그대로 적용하면 Pod 가 놓일 곳이 없어 멈춤
        dev = (b.targetDevice or '').strip()
        if dev and check_devices:
            known = known_nodes()
            if known is not None:
                cl, _, node = dev.rpartition('/')
                ok = (node in known) and (not cl or known[node] == cl)
                if not ok:
                    warnings.append(
                        f"maleBinding '{label}': UNKNOWN_TARGET_DEVICE targetDevice '{dev}' is not a current node "
                        f"(Analysis Engine heatmap); the pod cannot be placed until that device joins")
    return warnings


# 지금 있는 노드 이름 → 클러스터 (분석엔진 히트맵 /api/heatmap, 30초 캐시). 못 읽으면 None → 경고 안 함
_KNOWN_NODES = {'at': -1e9, 'map': None}


def known_nodes(ttl: float = 30.0):
    import json as _json, time as _time, urllib.request as _ur
    now = _time.monotonic()
    if now - _KNOWN_NODES['at'] < ttl:   # 실패(None)도 30초 기억 → 매 요청마다 다시 조회하지 않음
        return _KNOWN_NODES['map']
    base = settings.analysis_engine_addr().rstrip('/')
    try:
        with _ur.urlopen(base + '/api/heatmap', timeout=1.5) as r:
            rows = _json.load(r).get('rows') or []
        m = {x['node']: x.get('cluster') for x in rows if x.get('node')}
        _KNOWN_NODES.update(at=now, map=m or None)
    except Exception:
        _KNOWN_NODES.update(at=now, map=None)
    return _KNOWN_NODES['map']
