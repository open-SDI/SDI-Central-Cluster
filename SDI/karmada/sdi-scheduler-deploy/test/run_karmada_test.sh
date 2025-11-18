#!/usr/bin/env bash
set -Eeuo pipefail

# kubeconfig 경로(필요하면 환경변수로 덮어쓰기 가능)
KARMADA_KUBECONFIG="${KARMADA_KUBECONFIG:-/etc/karmada/karmada-apiserver.config}"

# kkc 별칭은 스크립트에서 확장되지 않으므로 함수로 정의
kkc() { kubectl --kubeconfig "${KARMADA_KUBECONFIG}" "$@"; }

# YAML들이 있는 디렉터리(기본: 현재 디렉터리)
DIR="${1:-.}"

# 파일명 (필요하면 환경변수로 덮어쓰기 가능)
NS_FILE="${NS_FILE:-namespace-default.yaml}"
POL_FILE="${POL_FILE:-test-workload-clusterpolicy.yaml}"
WL_FILE="${WL_FILE:-sdi-cluster-scheduler-test-workload.yaml}"

echo "==> Using kubeconfig: ${KARMADA_KUBECONFIG}"

# Karmada CRD 확인 (없으면 바로 중단)
if ! kkc get crd clusterpropagationpolicies.policy.karmada.io &>/dev/null; then
  echo "ERROR: Karmada CRDs not found in this context."
  echo "       Check kubeconfig path or Karmada installation."
  exit 1
fi

echo "==> Applying namespace (1/3): ${DIR}/${NS_FILE}"
kkc apply -f "${DIR}/${NS_FILE}"

echo "==> Applying cluster policy (2/3): ${DIR}/${POL_FILE}"
kkc apply -f "${DIR}/${POL_FILE}"

echo "==> Applying test workload (3/3): ${DIR}/${WL_FILE}"
kkc apply -f "${DIR}/${WL_FILE}"

echo "==> Current ResourceBindings"
kkc get resourcebindings -A

echo
echo "Tips:"
echo "  - 스케줄러 로그: kkc -n sdi-system logs deploy/sdi-cluster-scheduler -f"
echo "  - 멤버 클러스터 배포 확인: kubectl --context <member> -n default get deploy,pod"
