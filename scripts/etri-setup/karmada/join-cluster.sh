#!/bin/bash
# Karmada에 클러스터 조인 스크립트 (Airgap 환경 지원)
# 사용법: ./join-cluster.sh <클러스터-이름> <kubeconfig-경로> [SSH-호스트] [SSH-비밀번호]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KARMADACTL="${SCRIPT_DIR}/karmadactl"
KARMADA_KUBECONFIG="/etc/karmada/karmada-apiserver.config"

# 인자 확인
if [ -z "$1" ]; then
    echo -e "${RED}사용법: $0 <클러스터-이름> <kubeconfig-경로> [SSH-호스트] [SSH-비밀번호]${NC}"
    echo ""
    echo "예시:"
    echo "  # 로컬 kubeconfig 파일 사용"
    echo "  $0 edge-cluster /path/to/kubeconfig.yaml"
    echo ""
    echo "  # SSH로 원격 서버에서 kubeconfig 가져오기"
    echo "  $0 edge-cluster /etc/rancher/k3s/k3s.yaml root@10.0.0.39 ketilinux"
    exit 1
fi

CLUSTER_NAME="$1"
REMOTE_KUBECONFIG_PATH="$2"
SSH_HOST="$3"
SSH_PASSWORD="$4"

LOCAL_KUBECONFIG="${SCRIPT_DIR}/${CLUSTER_NAME}-kubeconfig.yaml"

echo "======================================"
echo "Karmada에 클러스터 조인"
echo "======================================"
echo "클러스터 이름: ${CLUSTER_NAME}"
echo ""

# 1. karmadactl 바이너리 확인
if [ ! -f "${KARMADACTL}" ]; then
    echo -e "${RED}✗ karmadactl 바이너리를 찾을 수 없습니다: ${KARMADACTL}${NC}"
    echo ""
    echo "외부망 있는 환경에서 다음을 실행하세요:"
    echo "  cd ${SCRIPT_DIR}/download-scripts"
    echo "  ./download-karmadactl.sh"
    exit 1
fi

# 2. Karmada 설치 확인
if [ ! -f "${KARMADA_KUBECONFIG}" ]; then
    echo -e "${RED}✗ Karmada가 설치되지 않았습니다.${NC}"
    echo "먼저 Karmada를 설치하세요:"
    echo "  ./install-karmada.sh"
    exit 1
fi

# 3. kubeconfig 가져오기
if [ -n "$SSH_HOST" ]; then
    echo -e "${YELLOW}1. SSH로 kubeconfig 가져오는 중...${NC}"
    
    # sshpass 설치 확인 (Airgap 환경에서는 미리 설치되어 있어야 함)
    if ! command -v sshpass &> /dev/null; then
        if [ -n "$SSH_PASSWORD" ]; then
            echo -e "${YELLOW}⚠ sshpass가 설치되어 있지 않습니다.${NC}"
            
            # 인터넷 연결 확인
            if timeout 3 curl -s --head http://archive.ubuntu.com > /dev/null 2>&1; then
                echo "sshpass 설치 중..."
                apt-get update -qq && apt-get install -y sshpass -qq
            else
                echo -e "${RED}✗ Airgap 환경에서는 sshpass를 미리 설치해야 합니다.${NC}"
                echo "외부망 있는 환경에서 다음을 실행하세요:"
                echo "  apt-get install -y sshpass"
                exit 1
            fi
        fi
    fi
    
    # SSH로 kubeconfig 가져오기
    if [ -n "$SSH_PASSWORD" ]; then
        sshpass -p "${SSH_PASSWORD}" scp -o StrictHostKeyChecking=no "${SSH_HOST}:${REMOTE_KUBECONFIG_PATH}" "${LOCAL_KUBECONFIG}"
    else
        scp -o StrictHostKeyChecking=no "${SSH_HOST}:${REMOTE_KUBECONFIG_PATH}" "${LOCAL_KUBECONFIG}"
    fi
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}✗ kubeconfig 가져오기 실패${NC}"
        exit 1
    fi
    
    # SSH 호스트에서 IP 추출
    CLUSTER_IP=$(echo "${SSH_HOST}" | sed 's/.*@//')
    
    # kubeconfig의 서버 주소 변경
    sed -i "s|https://127.0.0.1:6443|https://${CLUSTER_IP}:6443|g" "${LOCAL_KUBECONFIG}"
    
    echo -e "${GREEN}✓ kubeconfig 가져오기 완료${NC}"
else
    # 로컬 파일 사용
    if [ ! -f "${REMOTE_KUBECONFIG_PATH}" ]; then
        echo -e "${RED}✗ kubeconfig 파일을 찾을 수 없습니다: ${REMOTE_KUBECONFIG_PATH}${NC}"
        exit 1
    fi
    LOCAL_KUBECONFIG="${REMOTE_KUBECONFIG_PATH}"
fi
echo ""

# 4. 기존 클러스터 확인
echo -e "${YELLOW}2. 기존 클러스터 확인 중...${NC}"
if kubectl --kubeconfig="${KARMADA_KUBECONFIG}" get cluster "${CLUSTER_NAME}" &>/dev/null; then
    echo -e "${YELLOW}⚠ 클러스터 '${CLUSTER_NAME}'가 이미 등록되어 있습니다.${NC}"
    read -p "기존 클러스터를 삭제하고 재등록하시겠습니까? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        kubectl --kubeconfig="${KARMADA_KUBECONFIG}" delete cluster "${CLUSTER_NAME}"
        sleep 3
    else
        echo "조인을 취소합니다."
        exit 0
    fi
fi
echo ""

# 5. 클러스터 조인
echo -e "${YELLOW}3. 클러스터 조인 중...${NC}"
"${KARMADACTL}" --kubeconfig="${KARMADA_KUBECONFIG}" join "${CLUSTER_NAME}" --cluster-kubeconfig="${LOCAL_KUBECONFIG}"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 클러스터 '${CLUSTER_NAME}' 조인 완료${NC}"
else
    echo -e "${RED}✗ 클러스터 조인 실패${NC}"
    exit 1
fi
echo ""

# 6. 조인 상태 확인
echo -e "${YELLOW}4. 클러스터 상태 확인 중...${NC}"
sleep 5

kubectl --kubeconfig="${KARMADA_KUBECONFIG}" get clusters

echo ""
echo "======================================"
echo -e "${GREEN}클러스터 조인 성공!${NC}"
echo "======================================"
echo ""
echo "다음 명령어로 상세 정보를 확인하세요:"
echo "  kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config describe cluster ${CLUSTER_NAME}"
