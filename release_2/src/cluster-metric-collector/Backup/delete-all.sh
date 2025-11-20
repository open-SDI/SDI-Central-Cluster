#!/usr/bin/env bash
set -euo pipefail

# --- KKC 자동 감지/기본값 ---
# 1) KKC가 환경변수로 들어오면 그대로 사용
# 2) 아니면 시스템에 'kkc' 명령 있으면 사용
# 3) 둘 다 아니면 kubectl + karmada kubeconfig로 실행
if [[ -z "${KKC:-}" ]]; then
  if command -v kkc >/dev/null 2>&1; then
    KKC="kkc"
  else
    KKC="kubectl --kubeconfig /etc/karmada/karmada-apiserver.config"
  fi
fi

: "${MEMBER_CLUSTER_NAME:=k3s-cluster}"
: "${HOST_CLUSTER_NAME:=host}"
: "${NS:=monitor}"

echo "[Delete] Removing central Prometheus (host) and agent (member)..."
${KKC} -n "${NS}" delete deploy prom-central --ignore-not-found
${KKC} -n "${NS}" delete svc prom-central --ignore-not-found
${KKC} -n "${NS}" delete configmap prom-central-config --ignore-not-found
${KKC} delete propagationpolicy.policy.karmada.io -n "${NS}" prom-central-to-host --ignore-not-found

${KKC} -n "${NS}" delete deploy prom-agent --ignore-not-found
${KKC} -n "${NS}" delete svc prom-agent --ignore-not-found
${KKC} -n "${NS}" delete configmap prom-agent-config --ignore-not-found
${KKC} delete clusterrole prometheus --ignore-not-found
${KKC} delete clusterrolebinding prometheus --ignore-not-found
${KKC} -n "${NS}" delete serviceaccount prometheus --ignore-not-found
${KKC} delete propagationpolicy.policy.karmada.io -n "${NS}" prom-agent-to-members --ignore-not-found

echo "[Delete] Removing access token + PP..."
${KKC} -n "${NS}" delete secret karmada-access-token --ignore-not-found
${KKC} delete propagationpolicy.policy.karmada.io -n "${NS}" karmada-access-token-to-host --ignore-not-found

echo "[Delete] Removing Karmada SA/RBAC/token..."
${KKC} -n "${NS}" delete secret prom-karmada-token --ignore-not-found
${KKC} delete clusterrolebinding prom-karmada-cluster-proxy --ignore-not-found
${KKC} delete clusterrole prom-karmada-cluster-proxy --ignore-not-found
${KKC} -n "${NS}" delete serviceaccount prom-karmada --ignore-not-found

echo "[Delete] (Optional) Removing namespace propagation..."
${KKC} delete propagationpolicy.policy.karmada.io -n "${NS}" ns-${NS}-to-all --ignore-not-found
${KKC} delete ns "${NS}" --ignore-not-found

echo "Done."
