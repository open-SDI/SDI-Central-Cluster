#!/bin/bash
# Karmada 완전 삭제 스크립트

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KARMADACTL="${SCRIPT_DIR}/karmadactl"

echo "======================================"
echo "Karmada 완전 삭제"
echo "======================================"
echo ""

# 1. Member 클러스터 unjoin
echo -e "${YELLOW}1. Member 클러스터 unjoin 중...${NC}"
if [ -f "${KARMADACTL}" ] && [ -f "/etc/karmada/karmada-apiserver.config" ]; then
    CLUSTERS=$(kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config get clusters -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")
    
    if [ -n "$CLUSTERS" ]; then
        for cluster in $CLUSTERS; do
            echo "  - Unjoining cluster: ${cluster}"
            kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config delete cluster "${cluster}" 2>/dev/null || true
        done
        echo -e "${GREEN}✓ Member 클러스터 unjoin 완료${NC}"
    else
        echo "  - 등록된 클러스터가 없습니다."
    fi
else
    echo "  - Karmada가 설치되지 않았거나 이미 삭제되었습니다."
fi
echo ""

# 2. Karmada 네임스페이스 삭제
echo -e "${YELLOW}2. Karmada 네임스페이스 삭제 중...${NC}"
kubectl delete namespace karmada-system --force --grace-period=0 2>/dev/null || true
kubectl delete namespace karmada-cluster --force --grace-period=0 2>/dev/null || true
echo -e "${GREEN}✓ 네임스페이스 삭제 완료${NC}"
echo ""

# 3. Karmada CRDs 삭제
echo -e "${YELLOW}3. Karmada CRDs 삭제 중...${NC}"
kubectl delete crd $(kubectl get crd | grep karmada.io | awk '{print $1}') 2>/dev/null || true
kubectl delete crd $(kubectl get crd | grep multicluster.x-k8s.io | awk '{print $1}') 2>/dev/null || true
echo -e "${GREEN}✓ CRDs 삭제 완료${NC}"
echo ""

# 4. Webhook Configurations 삭제
echo -e "${YELLOW}4. Webhook Configurations 삭제 중...${NC}"
kubectl delete mutatingwebhookconfiguration mutating-config 2>/dev/null || true
kubectl delete validatingwebhookconfiguration validating-config 2>/dev/null || true
echo -e "${GREEN}✓ Webhook Configurations 삭제 완료${NC}"
echo ""

# 5. APIService 삭제
echo -e "${YELLOW}5. APIService 삭제 중...${NC}"
kubectl delete apiservice v1alpha1.cluster.karmada.io 2>/dev/null || true
echo -e "${GREEN}✓ APIService 삭제 완료${NC}"
echo ""

# 6. Karmada 설정 파일 삭제
echo -e "${YELLOW}6. Karmada 설정 파일 삭제 중...${NC}"
rm -rf /etc/karmada/ 2>/dev/null || true
echo -e "${GREEN}✓ 설정 파일 삭제 완료${NC}"
echo ""

# 7. 남아있는 리소스 확인
echo -e "${YELLOW}7. 남아있는 Karmada 리소스 확인...${NC}"
REMAINING_PODS=$(kubectl get pods -n karmada-system 2>/dev/null | wc -l)
REMAINING_NS=$(kubectl get ns | grep karmada | wc -l)

if [ "$REMAINING_PODS" -gt 0 ] || [ "$REMAINING_NS" -gt 0 ]; then
    echo -e "${YELLOW}⚠ 일부 리소스가 아직 삭제 중입니다. 잠시 후 다시 확인하세요.${NC}"
else
    echo -e "${GREEN}✓ 모든 Karmada 리소스가 삭제되었습니다.${NC}"
fi
echo ""

echo "======================================"
echo -e "${GREEN}Karmada 삭제 완료!${NC}"
echo "======================================"
echo ""
echo "확인 명령어:"
echo "  kubectl get ns | grep karmada"
echo "  kubectl get pods -n karmada-system"
echo "  kubectl get crd | grep karmada"

