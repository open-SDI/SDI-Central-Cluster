# SDI Analysis Engine 배포 가이드

이 디렉토리는 SDI Analysis Engine을 Kubernetes에 배포하고 관리하는 데 필요한 모든 파일들을 포함합니다.

## 📁 디렉토리 구조

```
/root/SDI/deploy/analysis-engine/
├── manifests/                    # Kubernetes 매니페스트 파일들
│   └── sdi-analysis-engine.yaml  # 메인 배포 파일 (Deployment, Service, ConfigMap, Secret)
├── scripts/                      # 배포 및 관리 스크립트들
│   └── deploy.sh                 # 메인 배포 스크립트
├── configs/                      # 설정 파일들
│   ├── influxdb-config.yaml      # InfluxDB 설정 ConfigMap
│   └── influxdb-secret.yaml      # InfluxDB 토큰 Secret
└── README.md                     # 이 파일
```

## 🚀 빠른 시작

### 1. 기본 배포

```bash
# 기본 배포 (기존 이미지 사용)
cd /root/SDI/deploy/analysis-engine
./scripts/deploy.sh deploy

# 전체 배포 (빌드 + 푸시 + 배포)
./scripts/deploy.sh full-deploy
```

### 2. 상태 확인

```bash
# 파드 상태 확인
./scripts/deploy.sh status

# 실시간 로그 확인
./scripts/deploy.sh logs

# 헬스체크
./scripts/deploy.sh health-check
```

### 3. 서비스 접속

```bash
# 포트 포워딩으로 로컬 접속
./scripts/deploy.sh port-forward

# 파드에 직접 접속
./scripts/deploy.sh exec
```

## 📋 배포 파일 설명

### `manifests/sdi-analysis-engine.yaml`

메인 배포 파일로 다음 리소스들을 포함합니다:

- **Deployment**: `sdi-analysis-engine`
  - 이미지: `ketidevit2/sdi-analysis-engine:v0.1.8`
  - 포트: 5000 (REST), 50051 (gRPC)
  - 환경변수: MALE_ACCURACY, MALE_LATENCY, MALE_ENERGY
  - 헬스체크: `/health` 엔드포인트

- **Service**: `sdi-analysis-engine-service`
  - 타입: NodePort
  - 포트: 30050 (REST), 30051 (gRPC)

- **ConfigMap**: `influxdb-config`
  - InfluxDB 연결 정보

- **Secret**: `influxdb-token`
  - InfluxDB 인증 토큰

## 🔧 스크립트 사용법

### `scripts/deploy.sh` - 메인 배포 스크립트

```bash
# 기본 사용법
./scripts/deploy.sh [명령어]

# 사용 가능한 명령어들
deploy         # 파드 배포 (kubectl apply만)
full-deploy    # 전체 배포 (빌드 + 푸시 + 버전업데이트 + 배포)
delete         # 파드 삭제
restart        # 파드 재시작
logs           # 파드 로그 확인 (실시간)
status         # 파드 상태 확인
build          # 도커 이미지만 빌드
push           # 도커 이미지 푸시 (빌드 포함)
update-version # YAML 파일의 이미지 버전 업데이트
exec           # 파드에 접속
port-forward   # 로컬 포트 포워딩 (50051:50051)
describe       # 파드 상세 정보
health-check   # 헬스체크 (REST API)
grpc-test      # gRPC 연결 테스트
```

## 🌐 서비스 접속 정보

### 외부 접속 (NodePort)

- **REST API**: `http://<node-ip>:30050`
- **gRPC**: `<node-ip>:30051`

### 로컬 접속 (포트 포워딩)

```bash
# 포트 포워딩 시작
./scripts/deploy.sh port-forward

# 별도 터미널에서 접속
curl http://localhost:5000/health
grpcurl -plaintext localhost:50051 list
```

## 🔍 모니터링 및 디버깅

### 상태 확인

```bash
# 파드 상태
kubectl get pods -l app=sdi-analysis-engine

# 서비스 상태
kubectl get svc -l app=sdi-analysis-engine

# 배포 상태
kubectl get deployment sdi-analysis-engine
```

### 로그 확인

```bash
# 실시간 로그
./scripts/deploy.sh logs

# 특정 파드 로그
kubectl logs <pod-name> -f
```

### 헬스체크

```bash
# REST API 헬스체크
./scripts/deploy.sh health-check

# gRPC 연결 테스트
./scripts/deploy.sh grpc-test
```

## 🛠️ 개발 및 빌드

### Docker 이미지 빌드

```bash
# 이미지만 빌드
./scripts/deploy.sh build

# 빌드 + 푸시
./scripts/deploy.sh push
```

### 버전 업데이트

```bash
# YAML 파일의 이미지 버전 업데이트
./scripts/deploy.sh update-version
```

## 📊 환경변수 설정

현재 설정된 환경변수들:

- `PYTHONUNBUFFERED=1`: Python 출력 버퍼링 비활성화
- `BOT=TURTLEBOT3-Burger-1`: 로봇 타입 설정
- `MALE_ACCURACY=700`: MALE 정확도 값
- `MALE_LATENCY=500`: MALE 지연시간 값
- `MALE_ENERGY=700`: MALE 전력효율 값

## 🔧 설정 변경

### MALE 값 변경

```bash
# YAML 파일에서 환경변수 수정
vim /root/SDI/deploy/analysis-engine/manifests/sdi-analysis-engine.yaml

# 파드 재시작
./scripts/deploy.sh restart
```

### InfluxDB 설정 변경

```bash
# ConfigMap 수정
vim /root/SDI/deploy/analysis-engine/configs/influxdb-config.yaml

# Secret 수정
vim /root/SDI/deploy/analysis-engine/configs/influxdb-secret.yaml

# 설정 적용
kubectl apply -f /root/SDI/deploy/analysis-engine/configs/
```

## 🚨 문제 해결

### 일반적인 문제들

#### 1. 파드가 시작되지 않는 경우

```bash
# 파드 상태 확인
kubectl describe pod <pod-name>

# 이벤트 확인
kubectl get events --sort-by=.metadata.creationTimestamp
```

#### 2. 서비스에 접속할 수 없는 경우

```bash
# 서비스 상태 확인
kubectl get svc sdi-analysis-engine-service

# 엔드포인트 확인
kubectl get endpoints sdi-analysis-engine-service
```

#### 3. 헬스체크 실패

```bash
# 파드 로그 확인
./scripts/deploy.sh logs

# 파드 내부에서 직접 테스트
./scripts/deploy.sh exec
curl http://localhost:5000/health
```

### 디버깅 명령어

```bash
# 파드 상세 정보
./scripts/deploy.sh describe

# 파드 접속하여 내부 확인
./scripts/deploy.sh exec

# 포트 포워딩으로 로컬 테스트
./scripts/deploy.sh port-forward
```

## 📚 관련 리소스

### 소스 코드

- **Analysis Engine**: `/root/SDI/analysis-engine/`
- **Dockerfile**: `/root/SDI/analysis-engine/Dockerfile`
- **Requirements**: `/root/SDI/analysis-engine/requirements.txt`

### 유용한 링크

- [Kubernetes 공식 문서](https://kubernetes.io/docs/)
- [Docker 공식 문서](https://docs.docker.com/)

## 🤝 기여하기

1. 이슈 리포트: 문제가 발생하면 상세한 로그와 함께 리포트해주세요.
2. 개선 제안: 새로운 기능이나 개선사항을 제안해주세요.
3. 테스트 케이스: 새로운 테스트 시나리오를 추가해주세요.

## 📄 라이선스

이 프로젝트는 Apache License 2.0 하에 배포됩니다.

---

**주의사항**: 이 배포 가이드는 테스트 환경을 기준으로 작성되었습니다. 프로덕션 환경에서 사용하기 전에 보안 설정과 리소스 제한을 적절히 조정하세요.
