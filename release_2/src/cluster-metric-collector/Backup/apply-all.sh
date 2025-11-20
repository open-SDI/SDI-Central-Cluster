#!/usr/bin/env bash
set -euo pipefail

# --- 설정 가능한 환경 변수 ---
: "${MEMBER_CLUSTER_NAME:=k3s-cluster}"
: "${HOST_CLUSTER_NAME:=host}"
: "${NS:=monitor}"
: "${KARMADA_SVC:=karmada-apiserver.karmada-system.svc}"
: "${KARMADA_PORT:=5443}"
# 'kkc' alias를 실제 kubectl 명령어로 수정
: "${KKC:=kubectl --kubeconfig /etc/karmada/karmada-apiserver.config}"
# --------------------------------------------------

# 스크립트가 위치한 디렉토리 경로
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# YAML 파일들이 있는 디렉토리 경로 지정
yaml_dir="${here}/yaml"
build_dir="${here}/.build"
mkdir -p "${build_dir}"

export MEMBER_CLUSTER_NAME HOST_CLUSTER_NAME NS KARMADA_SVC KARMADA_PORT

echo "[1/7] YAML 템플릿 렌더링..."
# 'yaml' 디렉토리에서 .yaml 파일을 찾아 처리
for f in "${yaml_dir}"/*.yaml; do
  out="${build_dir}/$(basename "$f")"
  envsubst < "$f" > "$out"
  echo "  - $(basename "$f") -> .build/$(basename "$f")"
done

echo "[2/7] 모든 클러스터에 Namespace와 PropagationPolicy 적용..."
${KKC} apply -f "${build_dir}/00-namespace-and-pp.yaml"

echo "[3/7] Karmada 프록시 접근을 위한 SA/RBAC/토큰 생성..."
${KKC} apply -f "${build_dir}/10-karmada-proxy-access.yaml"

echo "[4/7] ServiceAccount 토큰이 생성될 때까지 대기..."
# Secret에 토큰 필드가 생길 때까지 대기
for i in $(seq 1 60); do
  token_b64="$(${KKC} -n "${NS}" get secret prom-karmada-token -o jsonpath='{.data.token}' || true)"
  if [[ -n "${token_b64}" ]]; then
    break
  fi
  sleep 2
done
if [[ -z "${token_b64:-}" ]]; then
  echo "오류: prom-karmada-token에 토큰이 없습니다. 클러스터를 확인하고 다시 시도하세요."
  exit 1
fi
KARMADA_TOKEN="$(printf '%s' "${token_b64}" | base64 -d)"

echo "[4.1/7] SA 토큰으로 host 전용 Secret(karmada-access-token) 생성..."
${KKC} -n "${NS}" delete secret karmada-access-token --ignore-not-found
kubectl create secret generic karmada-access-token \
  --from-literal=token="${KARMADA_TOKEN}" \
  -n "${NS}" --dry-run=client -o yaml | ${KKC} apply -f -

echo "[4.2/7] 생성된 Secret을 host 클러스터에만 보내도록 PP 적용..."
${KKC} apply -f "${build_dir}/12-karmada-access-token-pp.yaml"

echo "[5/7] member 클러스터(${MEMBER_CLUSTER_NAME})에 Prometheus 에이전트 배포..."
${KKC} apply -f "${build_dir}/20-member-prom-agent.yaml"
${KKC} apply -f "${build_dir}/21-member-prom-agent-pp.yaml"

echo "[6/7] host 클러스터(${HOST_CLUSTER_NAME})에 중앙 Prometheus 배포..."
${KKC} apply -f "${build_dir}/30-central-prom.yaml"
${KKC} apply -f "${build_dir}/31-central-prom-pp.yaml"

echo "[7/7] 기본 상태 확인..."
set +e
${KKC} get --raw "/apis/cluster.karmada.io/v1alpha1/clusters/${MEMBER_CLUSTER_NAME}/proxy/api/v1/namespaces/${NS}/services/prom-agent:9090/proxy/-/ready" >/dev/null 2>&1 \
  && echo "  - Member prom-agent 준비 상태 엔드포인트 OK" \
  || echo "  - 경고: prom-agent 준비 상태 엔드포인트에 아직 연결할 수 없습니다."
set -e

echo
echo "==> 완료."
echo "host 클러스터의 중앙 Prometheus 서비스 (NodePort 30090):"
${KKC} -n "${NS}" get svc prom-central -o wide || true

echo
echo "Prometheus UI 주소: http://<HOST_클러스터_노드_IP>:30090"
echo "또는 port-forward 사용:"
echo "  ${KKC} -n ${NS} port-forward svc/prom-central 9090:9090"
echo
