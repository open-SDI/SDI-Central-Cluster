#!/bin/bash
# Karmada 상태 확인 스크립트

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

KARMADA_KUBECONFIG="/etc/karmada/karmada-apiserver.config"

echo "======================================"
echo "Karmada 상태 확인"
echo "======================================"
echo ""

# 1. Karmada 설치 확인
if [ -f "${KARMADA_KUBECONFIG}" ]; then
    echo -e "${GREEN}✓ Karmada가 설치되어 있습니다.${NC}"
else
    echo -e "${RED}✗ Karmada가 설치되지 않았습니다.${NC}"
    echo "설치 명령어: ./install-karmada.sh"
    exit 1
fi
echo ""

# 2. Karmada Pods 상태
echo "======================================"
echo "Karmada Pods 상태"
echo "======================================"
kubectl get pods -n karmada-system
echo ""

# 3. Karmada Services 상태
echo "======================================"
echo "Karmada Services 상태"
echo "======================================"
kubectl get svc -n karmada-system
echo ""

# 4. Member 클러스터 상태
echo "======================================"
echo "Member 클러스터 상태"
echo "======================================"
kubectl --kubeconfig="${KARMADA_KUBECONFIG}" get clusters
echo ""

# 5. 요약
echo "======================================"
echo "요약"
echo "======================================"

TOTAL_PODS=$(kubectl get pods -n karmada-system --no-headers 2>/dev/null | wc -l)
RUNNING_PODS=$(kubectl get pods -n karmada-system --no-headers 2>/dev/null | grep -c "Running" || echo "0")
TOTAL_CLUSTERS=$(kubectl --kubeconfig="${KARMADA_KUBECONFIG}" get clusters --no-headers 2>/dev/null | wc -l)
READY_CLUSTERS=$(kubectl --kubeconfig="${KARMADA_KUBECONFIG}" get clusters --no-headers 2>/dev/null | grep -c "True" || echo "0")

echo "Karmada Pods: ${RUNNING_PODS}/${TOTAL_PODS} Running"
echo "Member 클러스터: ${READY_CLUSTERS}/${TOTAL_CLUSTERS} Ready"

if [ "$RUNNING_PODS" -eq "$TOTAL_PODS" ] && [ "$TOTAL_PODS" -gt 0 ]; then
    echo -e "${GREEN}✓ Karmada가 정상 동작 중입니다.${NC}"
else
    echo -e "${YELLOW}⚠ 일부 Pod이 Running 상태가 아닙니다.${NC}"
fi

if [ "$TOTAL_CLUSTERS" -gt 0 ] && [ "$READY_CLUSTERS" -eq "$TOTAL_CLUSTERS" ]; then
    echo -e "${GREEN}✓ 모든 클러스터가 Ready 상태입니다.${NC}"
elif [ "$TOTAL_CLUSTERS" -gt 0 ]; then
    echo -e "${YELLOW}⚠ 일부 클러스터가 Ready 상태가 아닙니다.${NC}"
else
    echo -e "${YELLOW}⚠ 등록된 클러스터가 없습니다.${NC}"
    echo "클러스터 조인: ./join-cluster.sh <클러스터-이름> <kubeconfig-경로>"
fi

echo ""
echo "상세 정보 확인:"
echo "  kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config describe cluster <클러스터-이름>"

