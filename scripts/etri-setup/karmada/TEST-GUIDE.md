# Karmada 배포 테스트 가이드

## 🎯 테스트 스크립트 개요

Karmada를 통해 멀티 클러스터에 애플리케이션을 배포하고 확인하는 테스트 스크립트입니다.

### 제공되는 스크립트

| 스크립트 | 설명 |
|---------|------|
| `test-deployment.sh` | 테스트 애플리케이션 배포 |
| `verify-deployment.sh` | 배포 상태 실시간 확인 |
| `cleanup-test.sh` | 테스트 리소스 정리 |

---

## 🚀 빠른 시작

### 1. 테스트 배포 실행

```bash
cd /root/KETI_SDI_Central_Cluster/scripts/etri-setup/karmada
./test-deployment.sh
```

**수행 작업:**
1. Member 클러스터 확인
2. 테스트 네임스페이스 생성 (`karmada-test`)
3. Nginx Deployment 생성 (replica: 2)
4. PropagationPolicy 생성 (모든 클러스터에 배포)
5. 배포 상태 확인

### 2. 배포 상태 실시간 확인

```bash
./verify-deployment.sh
```

5초마다 자동으로 갱신되며, `Ctrl+C`로 종료합니다.

### 3. 테스트 리소스 정리

```bash
./cleanup-test.sh
```

---

## 📊 배포 확인 방법

### Karmada Control Plane에서 확인

```bash
# Deployment 상태
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config get deployment -n karmada-test

# ResourceBinding 상태 (어느 클러스터에 배포되었는지)
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config get resourcebinding -n karmada-test

# Work 상태 (실제 배포 작업)
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config get work -A | grep karmada-test

# 상세 정보
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config describe deployment nginx-test -n karmada-test
```

### Member 클러스터에서 직접 확인

**현재 클러스터 (중앙):**
```bash
kubectl get pods -n karmada-test -o wide
kubectl get deployment -n karmada-test
```

**원격 클러스터 (edge-cluster):**
```bash
# SSH로 접속
ssh root@10.0.0.39  # pw: ketilinux

# Pod 확인
kubectl get pods -n karmada-test -o wide
kubectl get deployment -n karmada-test
```

---

## 🔍 예상 결과

### 성공적인 배포

**Karmada Control Plane:**
```
NAME         READY   UP-TO-DATE   AVAILABLE   AGE
nginx-test   2/2     2            2           1m
```

**ResourceBinding:**
```
NAME                    SCHEDULED   FULLYAPPLIED   AGE
nginx-test-deployment   True        True           1m
```

**Member 클러스터 (edge-cluster):**
```
NAME                          READY   STATUS    RESTARTS   AGE
nginx-test-xxxxxxxxxx-xxxxx   1/1     Running   0          1m
nginx-test-xxxxxxxxxx-xxxxx   1/1     Running   0          1m
```

---

## 📝 테스트 시나리오

### 시나리오 1: 기본 배포 테스트

```bash
# 1. 배포
./test-deployment.sh

# 2. 상태 확인
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config get deployment -n karmada-test

# 3. 정리
./cleanup-test.sh
```

### 시나리오 2: 특정 클러스터에만 배포

수동으로 PropagationPolicy를 수정:

```bash
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config edit propagationpolicy nginx-propagation -n karmada-test
```

`clusterNames` 부분을 수정:
```yaml
placement:
  clusterAffinity:
    clusterNames:
      - edge-cluster  # 특정 클러스터만 지정
```

### 시나리오 3: 클러스터별 다른 replica 수

OverridePolicy 생성:

```bash
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config apply -f - <<EOF
apiVersion: policy.karmada.io/v1alpha1
kind: OverridePolicy
metadata:
  name: nginx-override
  namespace: karmada-test
spec:
  resourceSelectors:
    - apiVersion: apps/v1
      kind: Deployment
      name: nginx-test
  overrideRules:
    - targetCluster:
        clusterNames:
          - edge-cluster
      overriders:
        plaintext:
          - path: /spec/replicas
            operator: replace
            value: 3
EOF
```

---

## 🔧 문제 해결

### Deployment가 READY 0/2 상태

**원인**: Member 클러스터에 배포되지 않음

**확인:**
```bash
# ResourceBinding 확인
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config describe resourcebinding nginx-test-deployment -n karmada-test

# Work 확인
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config get work -A | grep karmada-test
```

**해결:**
1. Member 클러스터가 Ready 상태인지 확인
2. PropagationPolicy가 올바른지 확인
3. Karmada controller-manager 로그 확인

### Member 클러스터에 Pod이 없음

**원인**: Work가 생성되지 않았거나 실행되지 않음

**확인:**
```bash
# Work 상세 정보
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config describe work -n karmada-es-edge-cluster

# Karmada controller-manager 로그
kubectl logs -n karmada-system deployment/karmada-controller-manager
```

### PropagationPolicy 적용 안 됨

**원인**: resourceSelectors가 잘못됨

**확인:**
```bash
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config get propagationpolicy nginx-propagation -n karmada-test -o yaml
```

**수정:**
- `name`, `namespace`, `apiVersion`, `kind`가 정확한지 확인

---

## 📚 추가 테스트

### Service 배포

```bash
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: nginx-service
  namespace: karmada-test
spec:
  selector:
    app: nginx-test
  ports:
    - protocol: TCP
      port: 80
      targetPort: 80
  type: ClusterIP
---
apiVersion: policy.karmada.io/v1alpha1
kind: PropagationPolicy
metadata:
  name: nginx-service-propagation
  namespace: karmada-test
spec:
  resourceSelectors:
    - apiVersion: v1
      kind: Service
      name: nginx-service
  placement:
    clusterAffinity:
      clusterNames:
        - edge-cluster
EOF
```

### ConfigMap 배포

```bash
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: nginx-config
  namespace: karmada-test
data:
  index.html: |
    <html>
    <body>
    <h1>Hello from Karmada!</h1>
    </body>
    </html>
---
apiVersion: policy.karmada.io/v1alpha1
kind: PropagationPolicy
metadata:
  name: nginx-config-propagation
  namespace: karmada-test
spec:
  resourceSelectors:
    - apiVersion: v1
      kind: ConfigMap
      name: nginx-config
  placement:
    clusterAffinity:
      clusterNames:
        - edge-cluster
EOF
```

---

## 🎓 학습 포인트

### Karmada 주요 개념

1. **PropagationPolicy**: 어느 클러스터에 배포할지 결정
2. **ResourceBinding**: 배포 스케줄링 결과
3. **Work**: 실제 클러스터에 적용할 리소스
4. **OverridePolicy**: 클러스터별로 리소스 수정

### 배포 흐름

```
Deployment 생성
    ↓
PropagationPolicy 적용
    ↓
ResourceBinding 생성 (스케줄링)
    ↓
Work 생성 (각 클러스터별)
    ↓
Member 클러스터에 리소스 생성
```

---

## 📖 참고 문서

- [Karmada PropagationPolicy](https://karmada.io/docs/userguide/scheduling/resource-propagating)
- [Karmada OverridePolicy](https://karmada.io/docs/userguide/scheduling/override-policy)
- [Karmada 공식 문서](https://karmada.io/docs/)

---

## 💡 팁

### 빠른 확인 명령어

```bash
# 별칭 설정
alias k-karmada='kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config'

# 사용
k-karmada get clusters
k-karmada get deployment -n karmada-test
k-karmada get resourcebinding -n karmada-test
```

### Watch 모드

```bash
# Deployment 상태 실시간 확인
watch -n 2 'kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config get deployment -n karmada-test'

# Member 클러스터 Pod 실시간 확인
watch -n 2 'kubectl get pods -n karmada-test'
```

