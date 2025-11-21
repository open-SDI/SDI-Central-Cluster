# Karmada 설치 및 관리 가이드

Karmada v1.15.2를 Airgap 환경에서 설치하고 멀티 클러스터를 관리하기 위한 스크립트 모음입니다.

## 📁 디렉토리 구조

```
karmada/
├── karmadactl                      # Karmada CLI 바이너리 (v1.15.2)
├── download-scripts/               # 다운로드 스크립트 (외부망 필요)
│   ├── download-karmadactl.sh     # karmadactl 바이너리 다운로드
│   ├── download-karmada-images.sh # 컨테이너 이미지 다운로드
│   ├── download-karmada-crds.sh   # CRD 다운로드
│   └── README.md
├── install-karmada.sh              # Karmada 설치 (Airgap 자동 감지)
├── join-cluster.sh                 # 클러스터 조인 (범용)
├── uninstall-karmada.sh            # Karmada 완전 삭제
├── check-status.sh                 # 상태 확인
├── QUICKSTART.md                   # 빠른 시작 가이드
└── README.md                       # 이 파일
```

## 🚀 빠른 시작

**전체 과정은 [QUICKSTART.md](QUICKSTART.md)를 참고하세요.**

### 외부망 환경에서 (다운로드)

```bash
cd download-scripts
./download-karmadactl.sh
./download-karmada-images.sh
./download-karmada-crds.sh
cd ..
```

### Airgap 환경에서 (설치)

```bash
# Karmada 설치 (자동으로 Airgap 모드 감지)
./install-karmada.sh 10.0.5.55

# 클러스터 조인
./join-cluster.sh edge-cluster /etc/rancher/k3s/k3s.yaml root@10.0.0.39 ketilinux

# 상태 확인
./check-status.sh
```

---

## 📋 스크립트 상세 설명

### 1. 다운로드 스크립트 (download-scripts/)

#### `download-karmadactl.sh`
karmadactl 바이너리를 GitHub에서 다운로드합니다.

```bash
cd download-scripts
./download-karmadactl.sh
```

**생성 파일:**
- `../karmadactl` (~50MB)
- `../karmadactl-linux-amd64.tgz`

#### `download-karmada-images.sh`
모든 Karmada 컨테이너 이미지를 다운로드합니다.

```bash
./download-karmada-images.sh
```

**특징:**
- Docker 또는 containerd 자동 감지
- 10개 이미지 다운로드 및 tar 파일로 저장

**생성 파일:**
- `karmada-images-v1.15.2.tar` (~344MB)

#### `download-karmada-crds.sh`
Karmada CRD 파일을 다운로드합니다.

```bash
./download-karmada-crds.sh
```

**생성 파일:**
- `karmada-crds-v1.15.2.tar.gz` (~100KB)

---

### 2. 설치 스크립트

#### `install-karmada.sh`
Karmada를 설치합니다. 외부망 연결을 자동으로 감지하여 Airgap 모드로 동작합니다.

```bash
# API 서버 IP 자동 감지
./install-karmada.sh

# API 서버 IP 명시
./install-karmada.sh 10.0.5.55
```

**동작 방식:**
1. 외부망 연결 확인 (`curl` 테스트)
2. **Airgap 모드**: 
   - 로컬 이미지 파일 로드 (`ctr` 사용)
   - 로컬 CRD 파일 사용
3. **외부망 모드**: 
   - 자동으로 이미지 다운로드
   - 자동으로 CRD 다운로드

**필요 파일 (Airgap 모드):**
- `karmadactl` 바이너리
- `download-scripts/karmada-images-v1.15.2.tar`
- `download-scripts/karmada-crds-v1.15.2.tar.gz`

---

### 3. 클러스터 관리 스크립트

#### `join-cluster.sh`
Kubernetes 또는 k3s 클러스터를 Karmada에 조인합니다.

**사용법:**
```bash
./join-cluster.sh <클러스터-이름> <kubeconfig-경로> [SSH-호스트] [SSH-비밀번호]
```

**예시 1: SSH로 원격 k3s 클러스터 조인**
```bash
./join-cluster.sh edge-cluster /etc/rancher/k3s/k3s.yaml root@10.0.0.39 ketilinux
```

**예시 2: SSH로 원격 k8s 클러스터 조인**
```bash
./join-cluster.sh k8s-cluster /root/.kube/config root@10.0.0.50 password
```

**예시 3: 로컬 kubeconfig 파일 사용**
```bash
./join-cluster.sh my-cluster /path/to/kubeconfig.yaml
```

**예시 4: 현재 서버를 Member 클러스터로 등록**
```bash
./join-cluster.sh central-cluster /root/.kube/config
```

**동작 방식:**
1. SSH로 원격 서버에서 kubeconfig 가져오기 (선택사항)
2. kubeconfig의 서버 주소를 실제 IP로 변경
3. `karmadactl join` 실행

---

### 4. 관리 스크립트

#### `check-status.sh`
Karmada 및 Member 클러스터 상태를 확인합니다.

```bash
./check-status.sh
```

**출력 정보:**
- Karmada Pods 상태
- Karmada Services 상태
- Member 클러스터 목록 및 상태
- 요약 정보

#### `uninstall-karmada.sh`
Karmada를 완전히 삭제합니다.

```bash
./uninstall-karmada.sh
```

**삭제 항목:**
- Member 클러스터 unjoin
- karmada-system, karmada-cluster 네임스페이스
- Karmada CRDs
- Webhook Configurations
- APIService
- `/etc/karmada/` 디렉토리

---

## 📚 주요 명령어

### Karmada 관리

```bash
# Karmada 설치
./install-karmada.sh [API_SERVER_IP]

# 상태 확인
./check-status.sh

# Karmada 삭제
./uninstall-karmada.sh

# Karmada Pods 확인
kubectl get pods -n karmada-system

# Karmada Services 확인
kubectl get svc -n karmada-system
```

### 클러스터 관리

```bash
# 클러스터 조인
./join-cluster.sh <이름> <kubeconfig> [SSH-호스트] [SSH-비밀번호]

# 클러스터 목록
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config get clusters

# 클러스터 상세 정보
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config describe cluster <이름>

# 클러스터 삭제
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config delete cluster <이름>
```

---

## 🔧 문제 해결

### Karmada 설치 실패

#### "karmadactl 바이너리를 찾을 수 없습니다"

**원인**: karmadactl을 다운로드하지 않음

**해결:**
```bash
cd download-scripts
./download-karmadactl.sh
```

#### "이미지 파일을 찾을 수 없습니다" (Airgap 모드)

**원인**: 외부망 환경에서 이미지를 다운로드하지 않음

**해결:**
```bash
# 외부망 환경에서
cd download-scripts
./download-karmada-images.sh
```

#### "CRD 파일을 찾을 수 없습니다" (Airgap 모드)

**원인**: 외부망 환경에서 CRD를 다운로드하지 않음

**해결:**
```bash
# 외부망 환경에서
cd download-scripts
./download-karmada-crds.sh
```

#### "KUBECONFIG 설정 오류"

**원인**: KUBECONFIG 환경변수에 여러 경로가 설정됨

**해결:**
```bash
unset KUBECONFIG
./install-karmada.sh
```

또는
```bash
export KUBECONFIG=/root/.kube/config
./install-karmada.sh
```

---

### 클러스터 조인 실패

#### "cluster is not reachable" 또는 "Ready: False"

**원인**: kubeconfig의 서버 주소가 잘못됨 (127.0.0.1)

**해결:**
```bash
# kubeconfig 확인
grep server: <kubeconfig-파일>

# 127.0.0.1이면 실제 IP로 변경
sed -i 's|https://127.0.0.1:6443|https://실제IP:6443|g' <kubeconfig-파일>
```

#### "sshpass를 찾을 수 없습니다" (Airgap 환경)

**원인**: sshpass가 설치되지 않음

**해결:**
```bash
# 외부망 환경에서 미리 설치하거나
apt-get install -y sshpass

# SSH 비밀번호 없이 사용 (키 기반 인증)
./join-cluster.sh edge-cluster /etc/rancher/k3s/k3s.yaml root@10.0.0.39
```

---

### Pod이 Pending 상태

#### Control-plane taint 문제

**증상**: Karmada Pod이 계속 Pending

**해결:**
```bash
# Taint 확인
kubectl describe node <노드-이름> | grep -i taint

# Taint 제거
kubectl taint nodes <노드-이름> node-role.kubernetes.io/control-plane:NoSchedule-
```

#### 스케줄러 문제

**증상**: Pod이 스케줄링되지 않음

**해결:**
```bash
# 스케줄러 로그 확인
kubectl logs -n kube-system kube-scheduler-<노드-이름>

# containerd 및 kubelet 재시작
systemctl restart containerd
systemctl restart kubelet
```

---

## 📚 참고 정보

### 시스템 요구사항

- **Kubernetes**: v1.20 이상 (k3s 또는 k8s)
- **OS**: Ubuntu 22.04 LTS
- **Container Runtime**: containerd 1.7+
- **네트워크**: CNI 설치 필요 (Flannel, Calico 등)

### 포트 요구사항

- **5443**: Karmada API Server (NodePort: 32443)
- **2379-2380**: etcd
- **443**: Karmada Webhook, Aggregated API Server

### 주요 파일 위치

- **Karmada kubeconfig**: `/etc/karmada/karmada-apiserver.config`
- **Karmada 인증서**: `/etc/karmada/pki/`
- **CRD 파일**: `/etc/karmada/crds/`
- **k3s kubeconfig**: `/etc/rancher/k3s/k3s.yaml`
- **k8s kubeconfig**: `/root/.kube/config` 또는 `~/.kube/config`

### 다운로드 파일 크기

- `karmadactl`: ~50MB
- `karmada-images-v1.15.2.tar`: ~344MB
- `karmada-crds-v1.15.2.tar.gz`: ~100KB
- **총 약 394MB**

---

## 🎯 실제 사용 예시

### 예시 1: 완전한 Airgap 설치

**외부망 환경 (개발 PC):**
```bash
cd karmada/download-scripts
./download-karmadactl.sh
./download-karmada-images.sh
./download-karmada-crds.sh
cd ..

# Airgap 환경으로 전송
scp -r karmada/ root@10.0.5.55:/root/
```

**Airgap 환경 (중앙 클러스터):**
```bash
ssh root@10.0.5.55  # pw: ketilinux

cd /root/karmada
./install-karmada.sh 10.0.5.55
./join-cluster.sh edge-cluster /etc/rancher/k3s/k3s.yaml root@10.0.0.39 ketilinux
./check-status.sh
```

### 예시 2: 여러 클러스터 조인

```bash
# Edge 클러스터 1 (k3s)
./join-cluster.sh edge-1 /etc/rancher/k3s/k3s.yaml root@10.0.0.39 ketilinux

# Edge 클러스터 2 (k3s)
./join-cluster.sh edge-2 /etc/rancher/k3s/k3s.yaml root@10.0.0.40 ketilinux

# K8s 클러스터
./join-cluster.sh k8s-prod /root/.kube/config root@10.0.0.50 password

# 모든 클러스터 확인
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config get clusters
```

### 예시 3: 중앙 클러스터도 Member로 등록

```bash
# 중앙 클러스터 자체를 Member 클러스터로 등록
./join-cluster.sh central-cluster /root/.kube/config

# 확인
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config get clusters
```

---

## 🔍 유용한 링크

- **빠른 시작 가이드**: [QUICKSTART.md](QUICKSTART.md)
- **다운로드 스크립트 상세**: [download-scripts/README.md](download-scripts/README.md)
- **Karmada 공식 문서**: https://karmada.io/docs/
- **Karmada GitHub**: https://github.com/karmada-io/karmada
- **Karmada Releases**: https://github.com/karmada-io/karmada/releases

---

## 📝 버전 정보

- **Karmada**: v1.15.2
- **Kubernetes**: v1.20+ (k3s 또는 k8s)
- **작성일**: 2025-11-21
- **최종 업데이트**: 2025-11-21

---

## 💡 팁

### Airgap 환경 준비 체크리스트

외부망 환경에서 다음을 준비:
- [ ] `karmadactl` 바이너리
- [ ] `karmada-images-v1.15.2.tar` (344MB)
- [ ] `karmada-crds-v1.15.2.tar.gz` (100KB)
- [ ] `sshpass` 패키지 (선택사항)

### 이식성

이 디렉토리는 완전히 이식 가능합니다:
```bash
# 어디든 복사 가능
cp -r karmada/ /any/path/

# 복사한 위치에서 바로 실행
cd /any/path/karmada
./install-karmada.sh
```

모든 스크립트가 상대경로를 사용하므로 위치에 관계없이 동작합니다.
