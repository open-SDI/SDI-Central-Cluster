#!/bin/bash

# --- 설정 변수 (사용자 환경에 맞게 확인) ---
EDGE_SERVER_IP="10.0.0.39"
EDGE_SERVER_USER="root"
EDGE_KUBECONFIG_PATH="/etc/rancher/k3s/k3s.yaml"
# ---------------------------------------------

# 색상 코드
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}>> 1단계: K3s 엣지 클러스터($EDGE_SERVER_IP)의 kubeconfig 파일을 중앙 클러스터로 복사합니다.${NC}"
scp ${EDGE_SERVER_USER}@${EDGE_SERVER_IP}:${EDGE_KUBECONFIG_PATH} /tmp/kubeconfig.k3s-edge

if [ $? -ne 0 ]; then
    echo "오류: 엣지 클러스터에서 kubeconfig 파일을 가져오지 못했습니다. SSH 접속 정보와 사용자 권한을 확인하세요."
    exit 1
fi
echo -e "${GREEN}>> kubeconfig 파일 복사 완료! (/tmp/kubeconfig.k3s-edge)${NC}\n"


echo -e "${YELLOW}>> 2단계: 복사된 kubeconfig 파일의 서버 주소를 엣지 IP(${EDGE_SERVER_IP})로 변경합니다.${NC}"
# sed 명령어를 사용하여 '127.0.0.1'을 실제 엣지 서버 IP로 교체합니다.
sed -i "s/127.0.0.1/${EDGE_SERVER_IP}/g" /tmp/kubeconfig.k3s-edge
echo -e "${GREEN}>> 서버 주소 변경 완료!${NC}\n"


echo -e "${YELLOW}>> 3단계: 가져온 kubeconfig의 컨텍스트 이름을 'k3s-edge-cluster'로 변경합니다.${NC}"
CURRENT_CONTEXT=$(kubectl config get-contexts --kubeconfig=/tmp/kubeconfig.k3s-edge -o name)

if [ -z "$CURRENT_CONTEXT" ]; then
    echo "오류: 가져온 kubeconfig 파일에서 컨텍스트를 찾을 수 없습니다."
    exit 1
fi

kubectl config rename-context ${CURRENT_CONTEXT} k3s-edge-cluster --kubeconfig=/tmp/kubeconfig.k3s-edge
echo -e "${GREEN}>> 컨텍스트 이름 변경 완료! (새 이름: k3s-edge-cluster)${NC}\n"


echo -e "${YELLOW}>> 4단계: KUBECONFIG 환경 변수를 영구적으로 설정합니다.${NC}"
KUBECONFIG_LINE="export KUBECONFIG=~/.kube/config:/tmp/kubeconfig.k3s-edge"

if ! grep -qF "$KUBECONFIG_LINE" ~/.bashrc; then
    echo "$KUBECONFIG_LINE" >> ~/.bashrc
    echo -e "${GREEN}>> ~/.bashrc 파일에 KUBECONFIG 설정이 추가되었습니다.${NC}"
else
    echo -e "${GREEN}>> KUBECONFIG 설정이 이미 ~/.bashrc에 존재합니다.${NC}"
fi

echo -e "\n${GREEN}🎉 모든 설정이 완료되었습니다!${NC}"
echo -e "터미널을 새로 열거나 아래 명령어를 실행하여 설정을 적용하세요."
echo -e "${YELLOW}source ~/.bashrc${NC}"
