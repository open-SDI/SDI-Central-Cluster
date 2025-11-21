#!/bin/bash
# Karmada 설치 스크립트 (Airgap 환경 지원)
# 사용법: ./install-karmada.sh [API_SERVER_IP]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KARMADACTL="${SCRIPT_DIR}/karmadactl"
KUBECONFIG_PATH="${KUBECONFIG:-$HOME/.kube/config}"
KARMADA_VERSION="v1.15.2"
CRD_TAR="${SCRIPT_DIR}/download-scripts/karmada-crds-${KARMADA_VERSION}.tar.gz"
IMAGE_TAR="${SCRIPT_DIR}/download-scripts/karmada-images-${KARMADA_VERSION}.tar"

# API Server IP 자동 감지 또는 인자로 받기
if [ -n "$1" ]; then
    API_SERVER_IP="$1"
else
    # 현재 노드의 IP 자동 감지
    API_SERVER_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
fi

echo "======================================"
echo "Karmada ${KARMADA_VERSION} 설치"
echo "======================================"
echo "API Server IP: ${API_SERVER_IP}"
echo "Kubeconfig: ${KUBECONFIG_PATH}"
echo ""

# 1. karmadactl 바이너리 확인
echo -e "${YELLOW}1. karmadactl 바이너리 확인 중...${NC}"
if [ ! -f "${KARMADACTL}" ]; then
    echo -e "${RED}✗ karmadactl 바이너리를 찾을 수 없습니다: ${KARMADACTL}${NC}"
    echo ""
    echo "외부망 있는 환경에서 다음을 실행하세요:"
    echo "  cd ${SCRIPT_DIR}/download-scripts"
    echo "  ./download-karmadactl.sh"
    exit 1
fi
echo -e "${GREEN}✓ karmadactl 바이너리 확인 완료${NC}"
echo ""

# 2. Kubernetes 클러스터 연결 확인
echo -e "${YELLOW}2. Kubernetes 클러스터 연결 확인 중...${NC}"
if ! kubectl cluster-info &>/dev/null; then
    echo -e "${RED}✗ Kubernetes 클러스터에 연결할 수 없습니다.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Kubernetes 클러스터 연결 확인 완료${NC}"
echo ""

# 3. 기존 Karmada 설치 확인
echo -e "${YELLOW}3. 기존 Karmada 설치 확인 중...${NC}"
if kubectl get namespace karmada-system &>/dev/null; then
    echo -e "${YELLOW}⚠ Karmada가 이미 설치되어 있습니다.${NC}"
    read -p "기존 설치를 삭제하고 재설치하시겠습니까? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "기존 Karmada 삭제 중..."
        "${SCRIPT_DIR}/uninstall-karmada.sh"
        sleep 5
    else
        echo "설치를 취소합니다."
        exit 0
    fi
fi
echo -e "${GREEN}✓ 설치 가능${NC}"
echo ""

# 4. Airgap 환경 확인 및 이미지 로드
echo -e "${YELLOW}4. 컨테이너 이미지 확인 중...${NC}"

# 인터넷 연결 확인
if timeout 3 curl -s --head https://registry.k8s.io > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 외부망 연결 가능 - 이미지 자동 다운로드${NC}"
    AIRGAP_MODE=false
else
    echo -e "${YELLOW}⚠ 외부망 연결 불가 - Airgap 모드${NC}"
    AIRGAP_MODE=true
    
    # Airgap 모드에서 이미지 파일 확인
    if [ ! -f "${IMAGE_TAR}" ]; then
        echo -e "${RED}✗ 이미지 파일을 찾을 수 없습니다: ${IMAGE_TAR}${NC}"
        echo ""
        echo "외부망 있는 환경에서 다음을 실행하세요:"
        echo "  cd ${SCRIPT_DIR}/download-scripts"
        echo "  ./download-karmada-images.sh"
        exit 1
    fi
    
    # containerd에 이미지 로드
    echo "containerd에 이미지 로드 중..."
    if command -v ctr &> /dev/null; then
        ctr -n k8s.io images import "${IMAGE_TAR}"
        echo -e "${GREEN}✓ 이미지 로드 완료${NC}"
    else
        echo -e "${RED}✗ ctr 명령어를 찾을 수 없습니다.${NC}"
        exit 1
    fi
fi
echo ""

# 5. Karmada 설치
echo -e "${YELLOW}5. Karmada 설치 중...${NC}"
echo "이 작업은 몇 분 정도 소요될 수 있습니다..."
echo ""

# Airgap 모드에서는 로컬 CRD 사용
if [ "$AIRGAP_MODE" = true ]; then
    if [ ! -f "${CRD_TAR}" ]; then
        echo -e "${RED}✗ CRD 파일을 찾을 수 없습니다: ${CRD_TAR}${NC}"
        echo ""
        echo "외부망 있는 환경에서 다음을 실행하세요:"
        echo "  cd ${SCRIPT_DIR}/download-scripts"
        echo "  ./download-karmada-crds.sh"
        exit 1
    fi
    
    echo "로컬 CRD 사용: ${CRD_TAR}"
    "${KARMADACTL}" init \
        --kubeconfig="${KUBECONFIG_PATH}" \
        --karmada-apiserver-advertise-address="${API_SERVER_IP}" \
        --crds="${CRD_TAR}"
else
    "${KARMADACTL}" init \
        --kubeconfig="${KUBECONFIG_PATH}" \
        --karmada-apiserver-advertise-address="${API_SERVER_IP}"
fi

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ Karmada 설치 완료${NC}"
else
    echo ""
    echo -e "${RED}✗ Karmada 설치 실패${NC}"
    exit 1
fi
echo ""

# 6. 설치 확인
echo -e "${YELLOW}6. 설치 상태 확인 중...${NC}"
sleep 5

echo ""
echo "Karmada Pods:"
kubectl get pods -n karmada-system

echo ""
echo "Karmada Services:"
kubectl get svc -n karmada-system

echo ""
echo "======================================"
echo -e "${GREEN}Karmada 설치 성공!${NC}"
echo "======================================"
echo ""
echo "다음 단계:"
echo "1. Member 클러스터 조인:"
echo "   ./join-cluster.sh <클러스터-이름> <kubeconfig-경로> [SSH-호스트] [SSH-비밀번호]"
echo ""
echo "2. 클러스터 목록 확인:"
echo "   kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config get clusters"
echo ""
echo "3. 상태 확인:"
echo "   ./check-status.sh"
