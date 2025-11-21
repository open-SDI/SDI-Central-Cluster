# Karmada Airgap 설치 준비 스크립트

이 디렉토리에는 인터넷 연결 환경에서 실행할 수 있는 다운로드 스크립트가 포함되어 있습니다.

## 사용 방법

### 1. 이미지 다운로드

인터넷 연결 환경에서 다음 스크립트를 실행하여 Karmada 컨테이너 이미지를 다운로드합니다:

```bash
./download-karmada-images.sh
```

이 스크립트는 다음을 수행합니다:
- Karmada v1.15.2의 모든 필수 컨테이너 이미지 다운로드
- 이미지를 `karmada-images-v1.15.2.tar` 파일로 저장

### 2. CRD 다운로드

인터넷 연결 환경에서 다음 스크립트를 실행하여 Karmada CRD 파일을 다운로드합니다:

```bash
./download-karmada-crds.sh
```

이 스크립트는 다음을 수행합니다:
- Karmada v1.15.2의 CRD YAML 파일 다운로드
- `karmada-crds-v1.15.2.tar.gz` 파일로 저장

## Airgap 환경으로 전송

다운로드한 파일들을 airgap 환경으로 전송합니다:

```bash
# 이미지 파일 전송
scp karmada-images-v1.15.2.tar user@airgap-server:/root/KETI_SDI_Central_Cluster/scripts/etri-setup/karmada/

# CRD 파일 전송
scp karmada-crds-v1.15.2.tar.gz user@airgap-server:/root/KETI_SDI_Central_Cluster/scripts/etri-setup/karmada/
```

## 다운로드되는 이미지 목록

- `registry.k8s.io/kube-apiserver:v1.31.3` (karmada-apiserver가 사용)
- `docker.io/karmada/karmada-controller-manager:v1.15.2`
- `docker.io/karmada/karmada-scheduler:v1.15.2`
- `docker.io/karmada/karmada-webhook:v1.15.2`
- `docker.io/karmada/karmada-aggregated-apiserver:v1.15.2`
- `registry.k8s.io/kube-controller-manager:v1.31.3` (karmada-kube-controller-manager가 사용)
- `docker.io/karmada/karmada-descheduler:v1.15.2`
- `docker.io/karmada/karmada-metrics-adapter:v1.15.2`
- `docker.io/karmada/karmada-search:v1.15.2`
- `quay.io/coreos/etcd:v3.5.9`

**참고:** karmada-apiserver와 karmada-kube-controller-manager는 Kubernetes 공식 이미지를 사용합니다.

