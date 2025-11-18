#!/bin/bash

# --- 설정 ---
# 테스트용 Pod의 이름 (충돌을 피하기 위해 현재 시간 추가)
POD_NAME="scheduler-test-pod-$(date +%s)"
# 임시 YAML 파일 경로
YAML_FILE="/tmp/${POD_NAME}.yaml"
# Pod가 스케줄링될 때까지 기다릴 최대 시간 (초)
TIMEOUT=30

# --- 색상 코드 ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# --- 메인 스크립트 ---
echo -e "${YELLOW}>> 1. 테스트용 Pod 설정(Manifest) 파일을 생성합니다...${NC}"
cat << EOF > ${YAML_FILE}
apiVersion: v1
kind: Pod
metadata:
  name: ${POD_NAME}
spec:
  containers:
  - name: nginx
    image: nginx:1.14.2 # 가장 기본적인 이미지 사용
EOF
echo -e "${GREEN}   '${POD_NAME}' Pod 설정 생성 완료!${NC}\n"

echo -e "${YELLOW}>> 2. 테스트용 Pod를 클러스터에 배포합니다...${NC}"
kubectl apply -f ${YAML_FILE}
if [ $? -ne 0 ]; then
    echo -e "${RED}오류: Pod를 배포하지 못했습니다. kubectl 설정을 확인하세요.${NC}"
    # 임시 YAML 파일이 남지 않도록 실패 시에는 삭제
    rm -f "${YAML_FILE}"
    exit 1
fi
echo -e "${GREEN}   '${POD_NAME}' Pod 생성 요청 완료.${NC}\n"

echo -e "${YELLOW}>> 3. Pod가 노드에 할당(스케줄링)되기를 기다립니다... (최대 ${TIMEOUT}초)${NC}"
for (( i=0; i<${TIMEOUT}; i++ )); do
    NODE_NAME=$(kubectl get pod ${POD_NAME} -o jsonpath='{.spec.nodeName}' 2>/dev/null)

    if [[ ! -z "${NODE_NAME}" ]]; then
        echo -e "\n${GREEN}🎉 성공: Pod '${POD_NAME}'가 노드 '${NODE_NAME}'에 정상적으로 스케줄링되었습니다.${NC}"
        echo -e "\n${YELLOW}최종 Pod 상태:${NC}"
        kubectl get pod ${POD_NAME} -o wide
        
        echo -e "\n${YELLOW}>> 테스트가 완료되었습니다. 아래 명령어로 리소스를 직접 삭제해주세요:${NC}"
        echo "   kubectl delete pod ${POD_NAME}"
        echo "   rm ${YAML_FILE}"
        exit 0
    fi
    
    echo -n "."
    sleep 1
done

# --- 타임아웃 발생 시 ---
echo -e "\n${RED}❌ 실패: ${TIMEOUT}초 내에 Pod '${POD_NAME}'가 스케줄링되지 않았습니다.${NC}"
echo -e "\n${YELLOW}>> 디버깅을 위해 Pod의 상세 상태와 이벤트를 출력합니다:${NC}"
kubectl describe pod ${POD_NAME}

echo -e "\n${YELLOW}>> 테스트가 실패했습니다. 확인 후 아래 명령어로 리소스를 직접 삭제해주세요:${NC}"
echo "   kubectl delete pod ${POD_NAME}"
echo "   rm ${YAML_FILE}"
exit 1
