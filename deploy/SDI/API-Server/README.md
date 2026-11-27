# SDI Manifest Bridge

SDI Manifest Bridge는 단순화된 명세(Manifest)를 입력받아 쿠버네티스 환경에 적합한 전체 명세로 변환하고, 이를 클러스터에 배포하는 역할을 하는 API 서버입니다.

주로 Ansible과 같은 외부 도구로부터 간단한 요청을 받아, 내부적으로 사전에 정의된 템플릿과 결합하여 완전한 쿠버네티스 파드(Pod) 명세를 생성합니다. 이 과정에서 SDI(Software Defined Infrastructure) 환경에 필요한 특정 레이블(Label)과 어노테이션(Annotation)을 자동으로 추가하여, 전체 인프라와의 유기적인 연동을 지원합니다.

## 주요 기능

- **단순 명세 변환**: `mission`, `container_name`, `image` 등 최소한의 정보만으로 쿠버네티스 파드 명세를 생성합니다.
- **자동 인리치먼트(Enrichment)**: SDI에서 사용하는 `accuracy`, `latency`, `energy`와 같은 커스텀 어노테이션을 자동으로 추가합니다.
- **쿠버네티스 배포**: REST API 엔드포인트 (`/v1/apply`)를 통해 생성된 명세를 쿠버네티스 클러스터에 직접 배포(Server-Side Apply)합니다.
- **템플릿 기반 관리**: 파드 템플릿을 컨피그맵(ConfigMap)으로 관리하여, 배포 환경에 따라 유연하게 설정을 변경할 수 있습니다.

## 프로젝트 구조

```
.
├── kubernetes_manifests/ # 쿠버네티스 배포를 위한 명세 파일
│   ├── 00-namespace.yaml
│   ├── 01-rbac.yaml
│   ├── 02-configmap.yaml
│   ├── 03-deployment.yaml
│   └── 04-service.yaml
├── sdi_manifest_bridge/  # FastAPI 애플리케이션 소스 코드
│   ├── core/
│   │   ├── models.py         # IaCMaleBundle 입력 스키마
│   │   ├── validate.py       # 번들 정리 · 검증 · 경고 문자열
│   │   ├── convert.py        # MaleWorkload · PropagationPolicy 생성, 전달 보류, 적용 단계
│   │   ├── bundle.py         # 위 세 모듈을 다시 내보냄(예전 import 호환)
│   │   ├── consistency.py    # 일관성 경고 · 워크로드 분류 · 카탈로그/예측표로 빈 값 채우기
│   │   ├── enrichment.py     # 예전 단순 입력(/v1/apply) 변환
│   │   └── legacy_client.py  # 예전 단순 입력(/v1/apply) 전용 쿠버네티스 클라이언트
│   ├── k8s/client.py     # 번들 경로 쿠버네티스 클라이언트(Server-Side Apply)
│   ├── settings.py       # 환경 변수 스위치 모음
│   └── main.py           # API 엔드포인트 정의
├── tests/                # 테스트 코드
├── Dockerfile            # 컨테이너 이미지 빌드를 위한 Dockerfile
├── requirements.txt      # Python 의존성 목록
└── README.md             # 프로젝트 설명 파일
```

## 배포 방법

이 애플리케이션은 쿠버네티스 클러스터에 배포하는 것을 전제로 합니다. 아래의 `deploy.sh` 스크립트를 사용하여 관련 리소스를 한 번에 배포할 수 있습니다.

**요구사항**:
- `kubectl`이 설치되고, 타겟 클러스터에 대한 접근 권한이 설정되어 있어야 합니다.

**배포 명령어**:
```bash
# 스크립트에 실행 권한을 부여합니다.
chmod +x deploy.sh

# 스크립트를 실행하여 sdi-manifest-bridge 네임스페이스에 리소스를 배포합니다.
./deploy.sh
```

스크립트는 `kubernetes_manifests` 디렉토리의 YAML 파일들을 순서대로 적용하여, 독립된 `sdi-manifest-bridge` 네임스페이스에 모든 리소스를 생성합니다.

## 환경 변수 스위치

모두 `sdi_manifest_bridge/settings.py` 에 모여 있다. "켬" 값은 따로 적지 않으면 `on` · `true` · `1`(대소문자 무시).
"시작 때" 표시가 있는 값은 프로세스 시작 때 한 번 읽고, 나머지는 쓰일 때마다 읽는다.

| 변수 | 기본 | 하는 일 |
|---|---|---|
| `SDI_APPLY_MW_SEPARATE` | 꺼짐 | MaleWorkload 를 워크로드 다음 단계에 따로 적용(예전 4단계 순서) |
| `SDI_APPLY_POLICY_FIRST` | 꺼짐 | MaleWorkload + PropagationPolicy 를 워크로드보다 먼저 적용 |
| `SDI_HOLD_HC_DISPATCH` | 켬 | HC(등급 C) · 기체 지정 작업의 Karmada 전달 보류. `false` · `0` · `off` 일 때만 끔 |
| `SDI_HOLD_ALL_DISPATCH` | 꺼짐 | HC 가 아닌 작업도 전달 보류 |
| `SDI_PREPIN_TARGET` | 꺼짐 | "클러스터/노드" 기체 지정 작업은 보류하지 않음(Operator 가 미리 고정) |
| `SDI_HOLD_PREPINNED_NONHC` | 꺼짐 | `SDI_PREPIN_TARGET` 이 켜져 있어도 기체 지정 MC/LC 는 보류 |
| `SDI_HOLD_SKIP_EDGE_PATH` | 꺼짐 | `SDI_HOLD_ALL_DISPATCH` 가 켜져 있어도 placement edge · cloud 인 MC/LC 는 보류하지 않음 |
| `SDI_CATALOG_REFRESH_S` | `15` | 카탈로그 · 예측표를 뒤에서 다시 읽는 간격(초), `0` 이면 끔(시작 때) |
| `SDI_CATALOG_CONFIGMAP` | `karmada-system/sdi-workload-catalog` | 워크로드 카탈로그 ConfigMap(키 `catalog.yaml`) |
| `SDI_PREDICTIONS_CONFIGMAP` | `karmada-system/sdi-predictions` | 실행 시간 예측표 ConfigMap(키 `predictions.yaml`) |
| `ANALYSIS_ENGINE_ADDR` | `http://sdi-analysis-engine-i3.default.svc.cluster.local:5000` | 분석엔진 주소(render 의 장치 이름 확인, 30초 캐시) |
| `BRIDGE_APPLY_PRECHECK` | 꺼짐 | apply-bundle 전에 전체 dry-run 검사, 하나라도 틀리면 아무것도 적용하지 않고 422 (`yes` 도 켬) |
| `BRIDGE_THREADS` | `64` | 쿠버네티스 호출용 스레드 수(시작 때) |
| `BRIDGE_K8S_POOL_MAXSIZE` | `64` | 쿠버네티스 API 연결 풀 크기(시작 때) |
