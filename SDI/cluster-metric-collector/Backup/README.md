# Karmada 다중 클러스터 메트릭 (Cluster Proxy 기반 Prometheus Federation)

이 패키지는 다음을 생성합니다:

* host 및 member 클러스터에 **monitor** 네임스페이스
* 중앙 Prometheus가 **cluster proxy**를 호출할 수 있도록 하는 **Karmada ServiceAccount + RBAC**
* 각 멤버 클러스터에 **Prometheus 에이전트**(기본: `k3s-cluster`)
* 멤버 클러스터들의 메트릭을 연합(federation)으로 수집하는 host 클러스터의 **중앙 Prometheus**

## 빠른 시작

```bash
cd karmada-metrics
# (선택) 환경변수 수정: MEMBER_CLUSTER_NAME, HOST_CLUSTER_NAME, KARMADA_SVC, KARMADA_PORT
./apply-all.sh
```

## 기본값

* `MEMBER_CLUSTER_NAME=k3s-cluster`
* `HOST_CLUSTER_NAME=host`
* `NS=monitor`
* `KARMADA_SVC=karmada-apiserver.karmada-system.svc`
* `KARMADA_PORT=5443`

## 적용 후

* 중앙 Prometheus는 host 클러스터에서 NodePort **30090**으로 노출됩니다.
* Prometheus UI: `http://<임의의 host 노드 IP>:30090`

## 제거

```bash
./delete-all.sh
```
