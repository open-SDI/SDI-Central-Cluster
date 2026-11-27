"""
환경 변수 스위치 모음.

모든 SDI_* · BRIDGE_* 환경 변수의 이름과 읽는 함수를 여기에 둔다.
읽는 시점은 예전과 같다: 요청마다 읽던 값은 함수가 불릴 때마다 os.environ 을 읽고,
시작할 때 한 번 읽던 값(BRIDGE_THREADS · BRIDGE_K8S_POOL_MAXSIZE)은 그 모듈이 import 될 때 한 번 읽는다.
"""
import os

# --- 적용 순서 (core/convert.py) -------------------------------------------
# on: MaleWorkload 를 워크로드 다음 단계에 따로 적용(예전 4단계 순서). 기본 꺼짐
APPLY_MW_SEPARATE_ENV = 'SDI_APPLY_MW_SEPARATE'
# on: MaleWorkload + PropagationPolicy 를 워크로드보다 먼저 적용. 기본 꺼짐
APPLY_POLICY_FIRST_ENV = 'SDI_APPLY_POLICY_FIRST'

# --- 전달 보류 (core/convert.py) -------------------------------------------
# false|0|off: HC · 기체 지정 작업도 전달 보류를 걸지 않음. 기본 켬
HOLD_DISPATCH_ENV = 'SDI_HOLD_HC_DISPATCH'
# on: HC 가 아닌 작업도 전달 보류. 기본 꺼짐
HOLD_ALL_DISPATCH_ENV = 'SDI_HOLD_ALL_DISPATCH'
# on: "클러스터/노드" 기체 지정 작업은 Operator 가 미리 고정하므로 보류하지 않음. 기본 꺼짐
PREPIN_TARGET_ENV = 'SDI_PREPIN_TARGET'
# on: SDI_PREPIN_TARGET 이 켜져 있어도 기체 지정 MC/LC 는 보류. 기본 꺼짐
HOLD_PREPINNED_NONHC_ENV = 'SDI_HOLD_PREPINNED_NONHC'
# on: SDI_HOLD_ALL_DISPATCH 가 켜져 있어도 placement edge|cloud 인 MC/LC 는 보류하지 않음. 기본 꺼짐
HOLD_SKIP_EDGE_PATH_ENV = 'SDI_HOLD_SKIP_EDGE_PATH'

# --- 카탈로그 · 예측표 (core/consistency.py) --------------------------------
# 뒤에서 카탈로그 · 예측표를 다시 읽는 간격(초). 0 이면 끔. 기본 15
CATALOG_REFRESH_ENV = 'SDI_CATALOG_REFRESH_S'
# 워크로드 카탈로그 ConfigMap(<namespace>/<name>, 키 catalog.yaml)
CATALOG_CONFIGMAP_ENV = 'SDI_CATALOG_CONFIGMAP'
# 실행 시간 예측표 ConfigMap(<namespace>/<name>, 키 predictions.yaml)
PREDICTIONS_CONFIGMAP_ENV = 'SDI_PREDICTIONS_CONFIGMAP'

# --- 그 밖 ---------------------------------------------------------------
# 분석엔진 주소(장치 이름 확인용 /api/heatmap, core/validate.py)
ANALYSIS_ENGINE_ADDR_ENV = 'ANALYSIS_ENGINE_ADDR'
# 쿠버네티스 호출용 스레드 수(main.py, 시작 때 한 번). 기본 64
BRIDGE_THREADS_ENV = 'BRIDGE_THREADS'
# on|true|1|yes: apply-bundle 전에 전체 dry-run 검사(main.py). 기본 꺼짐
APPLY_PRECHECK_ENV = 'BRIDGE_APPLY_PRECHECK'
# 쿠버네티스 API 연결 풀 크기(k8s/client.py, 시작 때 한 번). 기본 64
K8S_POOL_MAXSIZE_ENV = 'BRIDGE_K8S_POOL_MAXSIZE'


def env_on(name: str) -> bool:
    """on · true · 1 이면 켬(대소문자 · 앞뒤 공백 무시). 없으면 꺼짐."""
    return os.environ.get(name, '').strip().lower() in ('on', 'true', '1')


def apply_mw_separate() -> bool:
    return env_on(APPLY_MW_SEPARATE_ENV)


def apply_policy_first() -> bool:
    return env_on(APPLY_POLICY_FIRST_ENV)


def hold_hc_dispatch_enabled() -> bool:
    """기본 켬. false · 0 · off 일 때만 끔."""
    return os.environ.get(HOLD_DISPATCH_ENV, '').strip().lower() not in ('false', '0', 'off')


def hold_all_dispatch() -> bool:
    return env_on(HOLD_ALL_DISPATCH_ENV)


def prepin_target() -> bool:
    return env_on(PREPIN_TARGET_ENV)


def hold_prepinned_nonhc() -> bool:
    return env_on(HOLD_PREPINNED_NONHC_ENV)


def hold_skip_edge_path() -> bool:
    return env_on(HOLD_SKIP_EDGE_PATH_ENV)


def catalog_refresh_s() -> float:
    return float(os.getenv(CATALOG_REFRESH_ENV, '15') or 0)


def catalog_configmap() -> str:
    return os.getenv(CATALOG_CONFIGMAP_ENV, 'karmada-system/sdi-workload-catalog')


def predictions_configmap() -> str:
    return os.getenv(PREDICTIONS_CONFIGMAP_ENV, 'karmada-system/sdi-predictions')


def analysis_engine_addr() -> str:
    return os.getenv(ANALYSIS_ENGINE_ADDR_ENV, 'http://sdi-analysis-engine-i3.default.svc.cluster.local:5000')


def bridge_threads() -> int:
    return int(os.environ.get(BRIDGE_THREADS_ENV, "64"))


def apply_precheck_enabled() -> bool:
    return os.environ.get(APPLY_PRECHECK_ENV, "off").strip().lower() in ("on", "true", "1", "yes")


def k8s_pool_maxsize() -> int:
    return int(os.environ.get(K8S_POOL_MAXSIZE_ENV, "64"))
