"""
번들 → 적용할 리소스 목록 변환.

- maleBindings → MaleWorkload CR (외부 API의 rtPeriodMs 등 단위 명시형 필드를 CRD 필드 rtPeriod 등으로 매핑,
  targetRef는 apiVersion/kind/name만 유지)
- Deployment 단위 PropagationPolicy 생성. Service/ConfigMap/Secret 등 support 리소스는 Deployment 가
  결정된 클러스터로 따라 보냄(propagateDeps). Service 는 Deployment annotation 에 이름을 적고
  ResourceInterpreterCustomization(karmada_manifests/sdi-deployment-dependencies.yaml)이 의존 리소스로 읽음
- 전달 보류(suspension.dispatching) 판단, 적용 단계(apply_order · apply_levels)
"""
import copy
import json
from typing import Any, Dict, List

from .. import settings
from ..settings import (  # noqa: F401  (예전 이름으로도 쓸 수 있게 다시 내보냄)
    APPLY_MW_SEPARATE_ENV, APPLY_POLICY_FIRST_ENV, PREPIN_TARGET_ENV,
    HOLD_DISPATCH_ENV, HOLD_ALL_DISPATCH_ENV, HOLD_PREPINNED_NONHC_ENV, HOLD_SKIP_EDGE_PATH_ENV,
    env_on as _env_on, hold_hc_dispatch_enabled,
)
from .models import IaCMaleBundle, MaleBinding, MCSpec
from .validate import _algorithm, normalize_bundle

MALE_GROUP = 'male.keti.dev'
# Deployment 가 쓰는 Service 이름(쉼표로 구분). ResourceInterpreterCustomization 이 의존 리소스로 읽는다
DEPENDENT_SERVICES_ANNOTATION = 'sdi.keti.dev/dependent-services'
MALE_VERSION = 'v1alpha1'

# 워크로드(스코어링 대상) 외의 kind는 support 리소스로 취급
SUPPORT_KINDS = {'ConfigMap', 'Secret', 'Service', 'PersistentVolumeClaim'}

# 적용 순서: ConfigMap/Secret -> Deployment(워크로드) + MaleWorkload -> PropagationPolicy
# 지켜야 하는 것은 "MaleWorkload 가 PP 보다 먼저"(스케줄러가 배치할 때 의도 · 등급을 읽음)뿐이다.
# Deployment 와 MaleWorkload 사이 순서는 필요 없으므로(Operator 는 대상이 아직 없으면 곧 다시 시도)
# 같은 단계에서 동시에 적용해 기다리는 단계를 하나 줄인다.
# 예전 4단계로 돌리려면 env SDI_APPLY_MW_SEPARATE=on.
APPLY_ORDER = {
    'Namespace': 0,
    'ConfigMap': 1,
    'Secret': 1,
    'PersistentVolumeClaim': 1,
    # 그 외 워크로드/Service = 2 (기본값)
    'MaleWorkload': 2,
    'PropagationPolicy': 4,
}
DEFAULT_ORDER = 2
# SDI_APPLY_POLICY_FIRST=on: Deployment 가 PP 보다 먼저 들어가면 Karmada detector 가 "정책 없음 대기 목록"에 넣었다가
# PP 가 오면 다시 찾아 RB 를 만들어 한 번 더 기다린다. on 이면 MaleWorkload + PP 를 먼저(2단계),
# 워크로드 · Service 를 마지막(3단계)에 넣어 Deployment 가 들어오자마자 RB 가 생기게 한다.
# MaleWorkload 는 여전히 RB(=스케줄링)보다 먼저 있다. 기본 off = 예전 순서.


def apply_order(kind: str) -> int:
    """리소스 종류의 적용 단계. env 로 MaleWorkload 를 예전처럼 따로 두거나, 정책을 워크로드보다 먼저 둘 수 있다."""
    if settings.apply_policy_first():
        if kind in ('MaleWorkload', 'PropagationPolicy'):
            return 2
        return APPLY_ORDER.get(kind, 3)
    if kind == 'MaleWorkload' and settings.apply_mw_separate():
        return 3
    return APPLY_ORDER.get(kind, DEFAULT_ORDER)


# HC 후보(요청 등급 C) 작업은 Karmada 전달을 잠시 보류(suspension.dispatching)한다.
# 이유: 결정 직후 Karmada 가 바로 엣지로 내려보내면 Operator 노드 고정(device-tier OverridePolicy)이 붙기 전에
# HC 파드가 잠깐 비실시간 노드(엣지 서버)에서 뜬다. Operator 가 고정 정책을 붙인 뒤 이 보류를 푼다.
# 이 annotation 이 붙은 정책만 Operator 가 푼다. Operator 의 시간 제한 안전장치는 스케줄러 결정이 아예 안 올 때만 쓰인다
# (후보 없음이면 계속 보류하고, 기기가 돌아오면 고정부터 만들고 푼다).
#
# 관련 스위치(settings.py):
# - SDI_HOLD_HC_DISPATCH: false|0|off 이면 보류하지 않음(기본 켬)
# - SDI_HOLD_ALL_DISPATCH: on 이면 HC 가 아닌 작업도 보류(기본 꺼짐)
# - SDI_PREPIN_TARGET: on 이면 "클러스터/노드" 기체 지정 작업은 보류하지 않음(Operator 가 결정 전에 고정, 기본 꺼짐)
# - SDI_HOLD_PREPINNED_NONHC: on 이면 "클러스터/노드" 기체 지정이라도 C(HC)가 아닌 작업은 보류(기본 꺼짐).
#   사전 고정은 device-tier 만 미리 만들고, 등급 · 실행 정책 · 중요도 같은 Pod 메타는 등급 계산 뒤에 붙는다.
#   보류 없이 먼저 전달되면 그 메타가 뒤따라 붙을 때 Pod 가 다시 만들어진다(ReplicaSet 2개).
#   HC 는 배치 지연을 줄이려고 이 경우에도 보류하지 않는다(실행 정책은 스케줄러 쪽에서 기다림).
#   보류는 Operator 가 Work 에 정책이 들어간 것을 보고 푼다.
# - SDI_HOLD_SKIP_EDGE_PATH: on 이면 배치 경로가 엣지 · 클라우드로 정해진(placement edge|cloud) 비 HC 작업은
#   SDI_HOLD_ALL_DISPATCH 가 켜져 있어도 보류하지 않는다. 이런 작업은 디바이스로 가지 않아 device-tier 고정이
#   생길 수 없고, Operator 파드 메타는 Work 생성보다 먼저 붙는다. 보류를 풀 때 생기는
#   PropagationPolicy → ResourceBinding → Work 쓰기 지연을 없앤다.
HOLD_DISPATCH_ANNOTATION = 'sdi.keti.dev/hold-dispatch'
HOLD_DISPATCH_VALUE = 'until-device-tier'

ANNO_MISSION_WORKLOAD = 'sdi.keti.dev/mission-workload'
ANNO_FILLED = 'sdi.keti.dev/filled'
ANNO_ALGORITHM = 'sdi.keti.dev/scheduler-algorithm'
# 기체 지정: 번들이 실행 기기를 정하면 스케줄러가 그 기기 행만 통과시킴. 값 = 노드 이름 또는 '클러스터/노드'
ANNO_TARGET_DEVICE = 'sdi.keti.dev/target-device'
ANNO_MISSION_TYPE = 'sdi.keti.dev/mission-type'
ANNO_MISSION_ATOMICITY = 'sdi.keti.dev/mission-atomicity'

# 등급 입력 전달: MALE Operator 등급 계산(internal/grade/grade.go InputFrom)은 안전 기능 · 역할 · 엄격도 · 경로 ·
# 작업 종류를 이 annotation 이나 카탈로그에서만 읽는다. 번들에 적힌 값이 등급에 들어가도록, **번들에 명시된 값만** 옮긴다
# (카탈로그 값은 Operator 가 직접 읽음. annotation 이 있으면 Operator 는 그 칸의 카탈로그 값을 쓰지 않음 = 번들 우선).
GRADE_ANNO = 'grade.male.keti.dev/'
_ROLE_TO_GRADE = {'core': 'core', 'support': 'assist', 'assist': 'assist', 'aux': 'aux'}
_PLACEMENT_TO_PATH = {'device': 'device-local', 'edge': 'edge', 'cloud': 'cloud'}


# ---------------------------------------------------------------------------
# 변환: maleBinding -> MaleWorkload CR, Deployment -> PropagationPolicy
# ---------------------------------------------------------------------------

def _build_maleworkload(bundle: IaCMaleBundle, binding: MaleBinding,
                        target: Dict[str, Any]) -> Dict[str, Any]:
    meta = target.get('metadata') or {}
    name = meta['name']
    namespace = meta.get('namespace', 'default')

    spec: Dict[str, Any] = {
        # 합의 사항: CRD targetRef에는 apiVersion/kind/name만 반영,
        # namespace는 MaleWorkload.metadata.namespace로 전달
        'targetRef': {
            'apiVersion': target['apiVersion'],
            'kind': target['kind'],
            'name': name,
        },
        'importance': binding.importance.model_dump(),
        'allowPolicyOverride': binding.allowPolicyOverride,
    }
    if binding.mission:
        spec['mission'] = binding.mission

    mc = binding.mcSpec
    targets = binding.maleTargets
    filled: Dict[str, Any] = dict(binding.normalizedFill)   # 기본값으로 채운 importance · criticality 출처
    if targets and targets.latencyBudgetMs and not (mc and mc.rtDeadlineMs):
        mc = (mc or MCSpec()).model_copy(update={'rtDeadlineMs': targets.latencyBudgetMs})
        filled['rtDeadline'] = {'value': targets.latencyBudgetMs, 'source': 'bundle-latencyBudget'}
    if mc:
        mc_spec: Dict[str, Any] = {}
        if mc.criticality:
            mc_spec['criticality'] = mc.criticality
        # 외부 API(단위 명시형) -> CRD 필드명 매핑
        if mc.rtPeriodMs is not None:
            mc_spec['rtPeriod'] = mc.rtPeriodMs
        if mc.rtWcetMs is not None:
            mc_spec['rtWcet'] = mc.rtWcetMs
        if mc.rtDeadlineMs is not None:
            mc_spec['rtDeadline'] = mc.rtDeadlineMs
        # 상위 미션 그룹핑: binding에 없으면 번들 missionId 사용
        mission_id = mc.missionId or bundle.missionId
        if mission_id:
            mc_spec['missionId'] = mission_id
        if mc_spec:
            spec['mcSpec'] = mc_spec
    elif bundle.missionId:
        spec['mcSpec'] = {'missionId': bundle.missionId}

    mw = {
        'apiVersion': f'{MALE_GROUP}/{MALE_VERSION}',
        'kind': 'MaleWorkload',
        'metadata': {
            'name': f'{name}-workload',
            'namespace': namespace,
            'labels': {'managed-by': 'sdi-manifest-bridge', 'sdi.keti.dev/bundle': bundle.bundleId},
        },
        'spec': spec,
    }
    ann: Dict[str, str] = {}
    algo = _algorithm(binding.schedulingAlgorithm or bundle.schedulingAlgorithm)
    if algo:
        ann[ANNO_ALGORITHM] = algo
    if binding.targetDevice and binding.targetDevice.strip():
        ann[ANNO_TARGET_DEVICE] = binding.targetDevice.strip()
    mws = _mission_workload_spec(binding, target)
    if mws:
        ann[ANNO_MISSION_WORKLOAD] = json.dumps(mws, ensure_ascii=False, sort_keys=True)
    if filled:
        ann[ANNO_FILLED] = json.dumps(filled, ensure_ascii=False, sort_keys=True)
    if bundle.missionType:
        ann[ANNO_MISSION_TYPE] = bundle.missionType
    if bundle.missionAtomicity:
        ann[ANNO_MISSION_ATOMICITY] = bundle.missionAtomicity   # 기록만(원자 배치는 아직 적용하지 않음)
    ann.update(grade_annotations(binding))
    if ann:
        mw['metadata']['annotations'] = ann
    return mw


def grade_annotations(binding: MaleBinding) -> Dict[str, str]:
    """번들에 명시된 C5 안전 · 역할, C4 엄격도, C6 실행 위치, C2 학습 · 배포 종류를 Operator 등급 입력 annotation 으로."""
    b = binding
    out: Dict[str, str] = {}
    if b.safety is True or b.usage == 'driving-perception':
        out['safety'] = 'true'          # R01 안전 기능 → HC
    elif b.safety is False:
        out['safety'] = 'false'
    if b.role and b.role.lower() in _ROLE_TO_GRADE:
        out['role'] = _ROLE_TO_GRADE[b.role.lower()]   # M 계수 · R05(aux 는 LC)
    if b.strictness:
        out['strictness'] = b.strictness.lower()       # R02(hard → 최소 MC) · R04(soft → 최대 MC)
    placement = (b.placement or '').lower()
    if placement in _PLACEMENT_TO_PATH:
        out['path'] = _PLACEMENT_TO_PATH[placement]    # R08: HC 는 device-local 만
    elif b.targetDevice and b.targetDevice.strip():
        out['path'] = 'device-local'                   # 기체 지정 = 그 기기에서 실행
    kind = (b.kind or '').lower()
    if kind == 'training':
        out['workload-class'] = 'split-training' if b.splitConfigs else 'training'   # R03 학습은 최대 MC
    elif kind == 'deploy':
        out['workload-class'] = 'model-deploy'
    return {GRADE_ANNO + k: v for k, v in out.items()}


def _resource_totals(target: Dict[str, Any]) -> Dict[str, Any]:
    """매니페스트 컨테이너 requests(없으면 limits) 의 cpu · memory · gpu 를 원문 그대로 모은다."""
    spec = target.get('spec') or {}
    pod = spec if target.get('kind') == 'Pod' else ((spec.get('template') or {}).get('spec') or {})
    out: Dict[str, Any] = {}
    for c in pod.get('containers') or []:
        res = c.get('resources') or {}
        for part in ('requests', 'limits'):
            for k, v in (res.get(part) or {}).items():
                key = 'gpu' if 'gpu' in k.lower() else k
                if key in ('cpu', 'memory', 'gpu') and key not in out:
                    out[key] = v
    return out


def _mission_workload_spec(binding: MaleBinding, target: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if binding.maleTargets:
        t = binding.maleTargets.model_dump(exclude_none=True)
        if t:
            out['maleTargets'] = t
    if binding.model:
        m = binding.model.model_dump(exclude_none=True)
        if m:
            out['model'] = m
    if out:
        r = _resource_totals(target)
        if r:
            out['resources'] = r
    return out


def _deployment_refs(manifest: Dict[str, Any]) -> Dict[str, set]:
    """Deployment pod spec이 참조하는 ConfigMap/Secret 이름을 수집한다."""
    refs = {'ConfigMap': set(), 'Secret': set()}
    pod_spec = (((manifest.get('spec') or {}).get('template') or {}).get('spec') or {})

    for vol in pod_spec.get('volumes') or []:
        if 'configMap' in vol:
            refs['ConfigMap'].add(vol['configMap'].get('name'))
        if 'secret' in vol:
            refs['Secret'].add(vol['secret'].get('secretName'))

    for container in (pod_spec.get('containers') or []) + (pod_spec.get('initContainers') or []):
        for env in container.get('env') or []:
            source = env.get('valueFrom') or {}
            if 'configMapKeyRef' in source:
                refs['ConfigMap'].add(source['configMapKeyRef'].get('name'))
            if 'secretKeyRef' in source:
                refs['Secret'].add(source['secretKeyRef'].get('name'))
        for env_from in container.get('envFrom') or []:
            if 'configMapRef' in env_from:
                refs['ConfigMap'].add(env_from['configMapRef'].get('name'))
            if 'secretRef' in env_from:
                refs['Secret'].add(env_from['secretRef'].get('name'))
    return refs


def _service_matches(service: Dict[str, Any], deployment: Dict[str, Any]) -> bool:
    """Service selector가 Deployment pod 라벨의 부분집합이면 해당 Deployment 소속으로 본다."""
    selector = (service.get('spec') or {}).get('selector') or {}
    if not selector:
        return False
    pod_labels = ((((deployment.get('spec') or {}).get('template') or {})
                   .get('metadata') or {}).get('labels') or {})
    return all(pod_labels.get(k) == v for k, v in selector.items())


def sdi_placement() -> Dict[str, Any]:
    """sdi-scheduler용 PropagationPolicy placement.

    알고리즘은 sdi-scheduler가 번들 의도와 히트맵으로 고르므로 clusterAffinities로 지정하지 않는다.
    점수 1위 클러스터 한 곳에만 전파하도록 cluster 그룹 수를 1로 고정한다.
    clusterTolerations는 비워 둔다(사용 중지 클러스터의 NoSchedule taint를 허용하지 않음).
    """
    return {
        'spreadConstraints': [
            {'spreadByField': 'cluster', 'maxGroups': 1, 'minGroups': 1},
        ],
        'clusterTolerations': [],
    }


def _build_propagationpolicy(bundle: IaCMaleBundle, deployment: Dict[str, Any],
                             support: List[Dict[str, Any]], hold: bool = False) -> Dict[str, Any]:
    meta = deployment['metadata']
    name = meta['name']
    namespace = meta.get('namespace', 'default')

    # 스코어링 루트는 Deployment. support 리소스는 결정된 클러스터로 함께 보낸다.
    # 기본: 정책에는 Deployment 만 두고 propagateDeps 로 따라 보냄. resourceSelectors 에 같이 넣으면
    # Karmada 가 리소스마다 ResourceBinding 을 따로 만들어 스케줄러가 다른 클러스터를 고를 수 있다
    follow = settings.support_follow_workload()
    selectors = [{'apiVersion': deployment['apiVersion'], 'kind': deployment['kind'], 'name': name}]
    for res in ([] if follow else support):
        selectors.append({
            'apiVersion': res['apiVersion'],
            'kind': res['kind'],
            'name': res['metadata']['name'],
        })

    policy = {
        'apiVersion': 'policy.karmada.io/v1alpha1',
        'kind': 'PropagationPolicy',
        'metadata': {
            'name': f'{name}-policy',
            'namespace': namespace,
            'labels': {'managed-by': 'sdi-manifest-bridge', 'sdi.keti.dev/bundle': bundle.bundleId},
        },
        'spec': {
            'resourceSelectors': selectors,
            'placement': sdi_placement(),
            'schedulerName': 'sdi-scheduler',
        },
    }
    if follow:
        policy['spec']['propagateDeps'] = True
    if hold:
        # 결정(스케줄링)은 그대로 하고 멤버 클러스터로 내려보내는 것만 멈춤. Operator 가 고정 후 해제
        policy['metadata']['annotations'] = {HOLD_DISPATCH_ANNOTATION: HOLD_DISPATCH_VALUE}
        policy['spec']['suspension'] = {'dispatching': True}
    return policy


def convert_bundle(bundle: IaCMaleBundle) -> List[Dict[str, Any]]:
    """
    검증을 통과한 번들을 실제 적용할 리소스 목록으로 변환한다.
    반환 순서 = 합의된 적용 순서 (ConfigMap/Secret -> 워크로드 -> MaleWorkload -> PropagationPolicy).
    """
    bundle, _, _ = normalize_bundle(bundle)   # 협의 규격 칸을 내부 칸으로(여러 번 불러도 같음)
    # 사본으로 다룸: Deployment 에 annotation 을 붙여도 호출한 쪽의 번들은 그대로
    manifests_by_id = {wm.id: copy.deepcopy(wm.manifest) for wm in bundle.workloadManifests}

    deployments = [m for m in manifests_by_id.values() if m.get('kind') == 'Deployment']
    supports = [m for m in manifests_by_id.values() if m.get('kind') in SUPPORT_KINDS]

    resources: List[Dict[str, Any]] = list(manifests_by_id.values())

    hold_names = set()
    for binding in bundle.maleBindings:
        target = manifests_by_id[binding.targetRef.manifestId]
        resources.append(_build_maleworkload(bundle, binding, target))
        # 기체 지정(targetDevice) 작업도 고정 전에 엣지 서버에 먼저 떴다가 옮겨질 수 있으므로(ReplicaSet 2개) 같이 보류
        hc = binding.mcSpec and binding.mcSpec.criticality == 'C'
        pinned = bool(binding.targetDevice and binding.targetDevice.strip())
        # "클러스터/노드" 기체 지정 작업은 Operator 가 결정 전에 고정하므로 보류하지 않음(SDI_PREPIN_TARGET=on)
        prepinned = pinned and '/' in binding.targetDevice.strip() and settings.prepin_target()
        # SDI_HOLD_ALL_DISPATCH=on 이면 MC/LC 도 보류 — 보류 없이 먼저 전달되면 Operator 의 실행 정책 · annotation 이
        # 뒤따라 붙을 때마다 Pod 가 다시 만들어짐(ReplicaSet 여러 개). 기본 꺼짐
        hold_all = settings.hold_all_dispatch()
        if prepinned and not hc and settings.hold_prepinned_nonhc():
            prepinned = False   # 기체 지정 MC/LC 는 사전 고정이 있어도 보류(Operator 메타가 Work 에 들어간 뒤 해제)
        edge_path = (binding.placement or '').strip().lower() in ('edge', 'cloud')
        if hold_all and not hc and not pinned and edge_path and settings.hold_skip_edge_path():
            hold_all = False    # 엣지 · 클라우드 경로가 정해진 MC/LC 는 보류하지 않음
        if hold_hc_dispatch_enabled() and (hc or pinned or hold_all) and not prepinned:
            hold_names.add(target['metadata']['name'])

    # 예전 방식(SDI_SUPPORT_FOLLOW_WORKLOAD=off): support 리소스는 참조하는 첫 Deployment 의 정책에만 포함
    # (중복 selector 방지). 기본 방식: 각 Deployment 가 쓰는 것 모두를 의존 리소스로(공유 리소스는 양쪽 클러스터로)
    follow = settings.support_follow_workload()
    claimed = set()
    for dep in deployments:
        refs = _deployment_refs(dep)
        owned = []
        for res in supports:
            key = (res['kind'], res['metadata']['name'])
            if key in claimed and not follow:
                continue
            kind = res['kind']
            if kind in ('ConfigMap', 'Secret') and res['metadata']['name'] in refs[kind]:
                owned.append(res)
                claimed.add(key)
            elif kind == 'Service' and _service_matches(res, dep):
                owned.append(res)
                claimed.add(key)
        services = sorted(r['metadata']['name'] for r in owned if r['kind'] == 'Service')
        if follow and services:
            dep.setdefault('metadata', {}).setdefault('annotations', {})[DEPENDENT_SERVICES_ANNOTATION] = ','.join(services)
        resources.append(_build_propagationpolicy(bundle, dep, owned, hold=dep['metadata']['name'] in hold_names))

    resources.sort(key=lambda r: apply_order(r.get('kind')))
    return resources


def apply_levels(resources: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """
    적용 순서(APPLY_ORDER) 단계별로 나눈다. 같은 단계의 리소스끼리는 서로 기다릴 이유가 없어
    동시에 적용하고, 단계 사이 순서(ConfigMap/Secret -> 워크로드 + MaleWorkload -> PropagationPolicy)는 지킨다.
    MaleWorkload 가 PropagationPolicy 보다 먼저여야 스케줄러가 배치할 때 의도와 등급을 읽을 수 있다.
    입력은 convert_bundle() 결과(이미 단계 순으로 정렬됨)라고 본다.
    """
    levels: List[List[Dict[str, Any]]] = []
    current = None
    for r in resources:
        order = apply_order(r.get('kind'))
        if order != current:
            levels.append([])
            current = order
        levels[-1].append(r)
    return levels


def resource_summary(resources: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """응답용 요약: 어떤 리소스가 어떤 순서로 적용되는지."""
    return [
        {
            'kind': r.get('kind', ''),
            'name': (r.get('metadata') or {}).get('name', ''),
            'namespace': (r.get('metadata') or {}).get('namespace', 'default'),
        }
        for r in resources
    ]
