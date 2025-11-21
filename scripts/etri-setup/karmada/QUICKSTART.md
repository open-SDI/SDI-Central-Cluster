# Karmada Airgap 설치 빠른 가이드

## 🎯 Airgap 환경 설치 과정

### 📥 1단계: 외부망 있는 환경에서 파일 다운로드

```bash
cd /path/to/karmada/download-scripts

# karmadactl 바이너리 다운로드
./download-karmadactl.sh

# 컨테이너 이미지 다운로드
./download-karmada-images.sh

# CRD 다운로드
./download-karmada-crds.sh
```

**다운로드되는 파일:**
- `karmadactl` - Karmada CLI 바이너리
- `karmada-images-v1.15.2.tar` - 모든 컨테이너 이미지 (약 500MB) -> containerd로 설치함함
- `karmada-crds-v1.15.2.tar.gz` - CRD 정의 파일

### 📦 2단계: Airgap 환경으로 전송

```bash
# karmada 디렉토리 전체를 Airgap 환경으로 전송
scp -r karmada/ root@10.0.5.55:/root/
```

또는 USB, 물리적 매체 등을 사용하여 전송

### 🚀 3단계: Airgap 환경에서 Karmada 설치

```bash
cd /root/karmada

# Karmada 설치 (자동으로 Airgap 모드 감지)
export KUBECONFIG=/root/.kube/config
./install-karmada-airgap.sh

# 또는 API 서버 IP 명시
./install-karmada-airgap.sh 10.0.5.55
```

**스크립트가 자동으로 수행:**
- 외부망 연결 확인
- Airgap 모드 감지
- containerd에 이미지 로드
- 로컬 CRD 사용하여 설치

### 🔗 4단계: 클러스터 조인

```bash
# SSH로 원격 클러스터 조인
./join-cluster.sh edge-cluster /etc/rancher/k3s/k3s.yaml root@10.0.0.39 ketilinux

# 또는 로컬 kubeconfig 파일 사용
./join-cluster.sh edge-cluster /path/to/kubeconfig.yaml
```

### ✅ 5단계: 상태 확인

```bash
./check-status.sh
```

---

## 📋 전체 명령어 요약

### 외부망 환경 (다운로드)

```bash
cd karmada/download-scripts
./download-karmadactl.sh
./download-karmada-images.sh
./download-karmada-crds.sh
cd ..
```

### Airgap 환경 (설치 및 조인)

```bash
cd karmada
./install-karmada.sh 10.0.5.55
./join-cluster.sh edge-cluster /etc/rancher/k3s/k3s.yaml root@10.0.0.39 ketilinux
./check-status.sh
```

---

## 🔧 주요 명령어

### Karmada 관리

```bash
# Karmada 설치 (Airgap 자동 감지)
./install-karmada.sh [API_SERVER_IP]

# 상태 확인
./check-status.sh

# Karmada 삭제
./uninstall-karmada.sh
```

### 클러스터 관리

```bash
# 클러스터 조인 (SSH 사용)
./join-cluster.sh <이름> <kubeconfig-경로> <SSH-호스트> <SSH-비밀번호>

# 클러스터 조인 (로컬 파일)
./join-cluster.sh <이름> <kubeconfig-경로>

# 클러스터 목록
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config get clusters

# 클러스터 삭제
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config delete cluster <이름>
```

---

## 🌐 실제 환경 예시

### 외부망 서버 (예: 개발 PC)

```bash
# 1. karmada 디렉토리로 이동
cd /path/to/karmada

# 2. 필요한 파일 다운로드
cd download-scripts
./download-karmadactl.sh
./download-karmada-images.sh
./download-karmada-crds.sh
cd ..

# 3. Airgap 환경으로 전송
scp -r ../karmada root@10.0.5.55:/root/
```

### Airgap 중앙 클러스터 (10.0.5.55)

```bash
# SSH 접속
ssh root@10.0.5.55  # pw: ketilinux

# Karmada 설치
cd /root/karmada
./install-karmada.sh 10.0.5.55

# Edge 클러스터 조인
./join-cluster.sh edge-cluster /etc/rancher/k3s/k3s.yaml root@10.0.0.39 ketilinux

# 상태 확인
./check-status.sh
```

### 예상 결과

```
======================================
Karmada 상태 확인
======================================

✓ Karmada가 설치되어 있습니다.

======================================
Karmada Pods 상태
======================================
NAME                                            READY   STATUS    RESTARTS   AGE
etcd-0                                          1/1     Running   0          5m
karmada-aggregated-apiserver-xxx                1/1     Running   0          4m
karmada-apiserver-xxx                           1/1     Running   0          5m
karmada-controller-manager-xxx                  1/1     Running   0          4m
karmada-scheduler-xxx                           1/1     Running   0          4m
karmada-webhook-xxx                             1/1     Running   0          4m
kube-controller-manager-xxx                     1/1     Running   0          4m

======================================
Member 클러스터 상태
======================================
NAME           VERSION        MODE   READY   AGE
edge-cluster   v1.33.4+k3s1   Push   True    3m

======================================
요약
======================================
Karmada Pods: 7/7 Running
Member 클러스터: 1/1 Ready
✓ Karmada가 정상 동작 중입니다.
✓ 모든 클러스터가 Ready 상태입니다.
```

---

## ⚠️ 주의사항

### Airgap 환경에서 필요한 사전 준비

1. **sshpass 설치** (SSH로 클러스터 조인 시)
   ```bash
   # 외부망 환경에서 미리 설치하거나 패키지 파일 준비
   apt-get install -y sshpass
   ```

2. **containerd 설치 및 실행**
   ```bash
   systemctl status containerd
   ```

3. **kubectl 설치**
   ```bash
   which kubectl
   ```

### 다운로드 파일 크기

- `karmadactl`: ~50MB
- `karmada-images-v1.15.2.tar`: ~500MB
- `karmada-crds-v1.15.2.tar.gz`: ~100KB

**총 약 550MB** 필요

---

## 🔍 문제 해결

### "이미지 파일을 찾을 수 없습니다"

**원인**: 외부망 환경에서 이미지를 다운로드하지 않음

**해결**:
```bash
# 외부망 환경에서
cd download-scripts
./download-karmada-images.sh
```

### "CRD 파일을 찾을 수 없습니다"

**원인**: 외부망 환경에서 CRD를 다운로드하지 않음

**해결**:
```bash
# 외부망 환경에서
cd download-scripts
./download-karmada-crds.sh
```

### "karmadactl 바이너리를 찾을 수 없습니다"

**원인**: karmadactl을 다운로드하지 않음

**해결**:
```bash
# 외부망 환경에서
cd download-scripts
./download-karmadactl.sh
```

### Pod이 Pending 상태

**원인**: Control-plane taint

**해결**:
```bash
kubectl taint nodes <노드-이름> node-role.kubernetes.io/control-plane:NoSchedule-
```

---

## 📚 더 자세한 정보

- 전체 가이드: [README.md](README.md)
- 다운로드 스크립트 상세: [download-scripts/README.md](download-scripts/README.md)
- Karmada 공식 문서: https://karmada.io/docs/
