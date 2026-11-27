"""
ETRI IaC + MALE Binding 번들 입력 API 지원 모듈 (open-SDI/SDI-MALE-Interface Issue #1 합의 사항).

실제 코드는 세 모듈에 나뉘어 있고, 이 모듈은 예전 import(`from .core.bundle import X`)가
그대로 동작하도록 이름을 다시 내보낸다.
  - models.py   : IaCMaleBundle(workloadManifests[] + maleBindings[]) 스키마
  - validate.py : 협의 규격 정리(normalize_bundle) · 검증(all-or-nothing) · 경고 문자열(bundle_warnings)
  - convert.py  : MaleWorkload · PropagationPolicy 생성, 전달 보류, 적용 단계
"""
from .models import (  # noqa: F401
    TargetRef, Importance, MCSpec, MaleTargets, ModelInfo, RTSpec, MissionRequirements,
    MaleBinding, WorkloadManifest, IaCMaleBundle,
)
from .validate import (  # noqa: F401
    IMPORTANCE_SUM_TOLERANCE, SCHEDULING_ALGORITHMS, MISSION_TYPE_IMPORTANCE, DEFAULT_IMPORTANCE,
    MISSION_ATOMICITY, PLACEMENT_ALIASES, PLACEMENT_VALUES,
    normalize_bundle, _algorithm, validate_bundle, bundle_warnings, _KNOWN_NODES, known_nodes,
)
from .convert import (  # noqa: F401
    MALE_GROUP, MALE_VERSION, SUPPORT_KINDS, APPLY_ORDER, DEFAULT_ORDER,
    APPLY_MW_SEPARATE_ENV, APPLY_POLICY_FIRST_ENV, PREPIN_TARGET_ENV,
    HOLD_DISPATCH_ANNOTATION, HOLD_DISPATCH_VALUE, HOLD_DISPATCH_ENV, HOLD_ALL_DISPATCH_ENV,
    HOLD_PREPINNED_NONHC_ENV, HOLD_SKIP_EDGE_PATH_ENV,
    ANNO_MISSION_WORKLOAD, ANNO_FILLED, ANNO_ALGORITHM, ANNO_TARGET_DEVICE, ANNO_MISSION_TYPE,
    ANNO_MISSION_ATOMICITY, GRADE_ANNO, _ROLE_TO_GRADE, _PLACEMENT_TO_PATH,
    _env_on, apply_order, hold_hc_dispatch_enabled,
    _build_maleworkload, grade_annotations, _resource_totals, _mission_workload_spec,
    _deployment_refs, _service_matches, sdi_placement, _build_propagationpolicy,
    convert_bundle, apply_levels, resource_summary,
)
