"""
IaCMaleBundle 입력 스키마(pydantic 모델).

open-SDI/SDI-MALE-Interface Issue #1 합의 형태: workloadManifests[] + maleBindings[].
협의 규격 칸(criticality · rtSpec · missionRequirements · placement deviceLocked/flexible)과
예전 칸(mcSpec · maleTargets · placement device/any/edge/cloud)을 모두 받는다.
협의 규격 칸을 내부 칸으로 옮기는 일은 validate.normalize_bundle 이 한다.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TargetRef(BaseModel):
    # manifestId만 필수. 나머지는 매니페스트에서 유도하며, 함께 주면 대조 검증(불일치 시 거부)
    manifestId: str
    apiVersion: Optional[str] = None
    kind: Optional[str] = None
    namespace: Optional[str] = None
    name: Optional[str] = None


class Importance(BaseModel):
    accuracy: float = Field(ge=0.0, le=1.0)
    latency: float = Field(ge=0.0, le=1.0)
    energy: float = Field(ge=0.0, le=1.0)


class MCSpec(BaseModel):
    criticality: Optional[str] = None
    # 외부 API는 단위 명시형(합의 사항). CRD 변환 시 rtPeriod 등으로 매핑됨.
    rtPeriodMs: Optional[int] = Field(default=None, ge=0)
    rtWcetMs: Optional[int] = Field(default=None, ge=0)
    rtDeadlineMs: Optional[int] = Field(default=None, ge=0)
    missionId: Optional[str] = None


# MissionWorkload 명세 항목: MALE 목표(Target Accuracy, Latency Budget, Power Budget 등),
# 모델 정보(Model Type, Model Size, 연산량). 모두 선택 칸.
# MaleWorkload annotation sdi.keti.dev/mission-workload 에 JSON 으로 남긴다(CRD 는 바꾸지 않음).
# latencyBudgetMs 는 rtDeadlineMs 가 없을 때 마감으로 쓴다(출처 bundle-latencyBudget).
class MaleTargets(BaseModel):
    targetAccuracy: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    latencyBudgetMs: Optional[int] = Field(default=None, gt=0)
    powerBudgetW: Optional[float] = Field(default=None, gt=0)
    # 작업별 배터리 의도값: 실행 기기 최소 배터리 % · 남은 미션 시간(초)
    minBatteryPct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    missionDurationS: Optional[float] = Field(default=None, gt=0)


class ModelInfo(BaseModel):
    type: Optional[str] = None             # 예: yolov5s, resnet50
    sizeMB: Optional[float] = Field(default=None, gt=0)
    gflops: Optional[float] = Field(default=None, gt=0)  # 추론 1회 연산량


# 협의 규격: 생성 단계에서는 미션 요구만 선언
class RTSpec(BaseModel):
    periodMs: Optional[int] = Field(default=None, gt=0)    # 정상 실행 주기
    deadlineMs: Optional[int] = Field(default=None, gt=0)  # job 발생 시점 기준 상대 마감(deadline > period 도 허용)


class MissionRequirements(BaseModel):
    minBatteryPct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    missionDurationS: Optional[float] = Field(default=None, gt=0)
    latencyBudgetMs: Optional[int] = Field(default=None, gt=0)
    targetAccuracy: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class MaleBinding(BaseModel):
    id: Optional[str] = None
    targetRef: TargetRef
    mission: Optional[str] = None
    # 협의 규격에서는 선택. 없으면 missionType 기본값 → 같은 비중(normalize_bundle, 채운 출처는 filled 에 기록)
    importance: Optional[Importance] = None
    mcSpec: Optional[MCSpec] = None
    # 협의 규격 칸(내부에서는 mcSpec · maleTargets 로 옮김)
    criticality: Optional[str] = None
    rtSpec: Optional[RTSpec] = None
    missionRequirements: Optional[MissionRequirements] = None
    allowPolicyOverride: bool = True
    schedulingAlgorithm: Optional[str] = None  # 없으면 번들 값, 그것도 없으면 스케줄러가 고름
    targetDevice: Optional[str] = None  # 기체 지정. 예: rpi5-npu-01, edge-cluster-a/rpi5-npu-01
    # 워크로드 분류 입력(분류 축 C1 ~ C9 의 항목 이름). 모두 선택 칸(KETI 제안)
    missionKind: Optional[str] = None   # C1 미션 계열: ai-split(AI 분업) | drive(구동)
    kind: Optional[str] = None          # C2 처리 형태: inference | training | deploy | control | service
    trigger: Optional[str] = None       # C3 이벤트형 계기(있으면 이벤트형)
    rounds: Optional[int] = Field(default=None, gt=0)   # C3 배치형(학습 라운드 수 등)
    strictness: Optional[str] = None    # C4 마감 엄격도: hard | firm | soft
    safety: Optional[bool] = None       # C5 안전 기능 표시
    usage: Optional[str] = None         # C5 용도(driving-perception 이면 안전 기능)
    role: Optional[str] = None          # C5 core | support | aux
    placement: Optional[str] = None     # C6 device | any | edge
    splitConfigs: Optional[List[Dict[str, Any]]] = None  # C8 분할 구성
    checkpoint: Optional[Dict[str, Any]] = None          # C9 {"supported": true|false}
    stateful: Optional[bool] = None     # C9 상태 있음
    maleTargets: Optional[MaleTargets] = None
    model: Optional[ModelInfo] = None
    # normalize_bundle 이 채운 칸과 출처(응답 · 입력 스키마에는 안 나옴)
    normalizedFill: Dict[str, Any] = Field(default_factory=dict, exclude=True)


class WorkloadManifest(BaseModel):
    id: str
    manifest: Dict[str, Any]


class IaCMaleBundle(BaseModel):
    apiVersion: str = 'sdi.keti.dev/v1alpha1'
    kind: str = 'IaCMaleBundle'
    bundleId: str
    # 상위 미션 ID (서브미션 그룹핑용, KETI 제안 규약 - 선택 필드로 하위 호환 유지)
    missionId: Optional[str] = None
    targetProfile: Optional[str] = None
    schedulingAlgorithm: Optional[str] = None  # 번들 전체 기본 알고리즘(바인딩 값이 우선)
    # 협의 규격: 미션 유형(ALE 기본 가중치) · 원자성(gang | criticalOnly | bestEffort)
    missionType: Optional[str] = None
    missionAtomicity: Optional[str] = None
    workloadManifests: List[WorkloadManifest] = Field(min_length=1)
    maleBindings: List[MaleBinding] = Field(default_factory=list)
