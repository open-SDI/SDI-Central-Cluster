#!/bin/bash

#############################################
# Kubernetes IP 자동 변경 스크립트
# 외부 네트워크 없이 작동
#############################################

set -e

echo "======================================"
echo "Kubernetes IP 자동 변경 스크립트"
echo "======================================"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 현재 IP 자동 감지 또는 수동 입력
get_current_ip() {
    # 명령줄 인자로 IP가 제공되면 그것을 사용
    if [ -n "$1" ]; then
        echo "$1"
        return
    fi

    # 자동 감지: 모든 네트워크 인터페이스에서 IP 찾기
    # localhost, docker, kubernetes 내부 IP 제외
    NEW_IP=$(ip -4 addr show | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | \
             grep -v '^127\.' | \
             grep -v '^172\.1[67]\.' | \
             grep -v '^10\.244\.' | \
             grep -v '^10\.96\.' | \
             grep -v '^169\.254\.' | \
             head -1)

    echo "$NEW_IP"
}

# 기존 IP 찾기
get_old_ip() {
    if [ -f /etc/kubernetes/admin.conf ]; then
        OLD_IP=$(grep -oP 'server: https://\K[0-9.]+' /etc/kubernetes/admin.conf | head -1)
        echo "$OLD_IP"
    fi
}

# IP 변경 함수
change_ip() {
    local OLD_IP=$1
    local NEW_IP=$2

    echo -e "${YELLOW}설정 파일 IP 변경 중: $OLD_IP → $NEW_IP${NC}"

    # Kubernetes 설정 파일 변경
    for file in /etc/kubernetes/manifests/*.yaml \
                /etc/kubernetes/*.conf \
                /etc/kubernetes/pki/*.conf; do
        if [ -f "$file" ]; then
            sed -i "s/$OLD_IP/$NEW_IP/g" "$file"
            echo "  ✓ $(basename $file)"
        fi
    done

    # kubelet 설정 변경
    if [ -f /var/lib/kubelet/kubeadm-flags.env ]; then
        # 기존 node-ip 플래그 제거 후 추가
        sed -i "s/--node-ip=[0-9.]*//g" /var/lib/kubelet/kubeadm-flags.env
        sed -i "s/\"$/ --node-ip=$NEW_IP\"/" /var/lib/kubelet/kubeadm-flags.env
        # 중복 공백 제거
        sed -i 's/  */ /g' /var/lib/kubelet/kubeadm-flags.env
        echo "  ✓ kubelet node-ip 설정"
    fi

    # kubelet config.yaml 수정 (있는 경우)
    if [ -f /var/lib/kubelet/config.yaml ]; then
        sed -i "s/$OLD_IP/$NEW_IP/g" /var/lib/kubelet/config.yaml
        echo "  ✓ kubelet config.yaml"
    fi
}

# 인증서 재생성
regenerate_certs() {
    local NEW_IP=$1

    echo -e "${YELLOW}API 서버 인증서 재생성 중...${NC}"

    # 기존 인증서 백업
    if [ -f /etc/kubernetes/pki/apiserver.crt ]; then
        mv /etc/kubernetes/pki/apiserver.crt /etc/kubernetes/pki/apiserver.crt.bak.$(date +%Y%m%d%H%M%S)
        mv /etc/kubernetes/pki/apiserver.key /etc/kubernetes/pki/apiserver.key.bak.$(date +%Y%m%d%H%M%S)
    fi

    # 인증서 재생성
    kubeadm init phase certs apiserver \
        --apiserver-advertise-address=$NEW_IP \
        --apiserver-cert-extra-sans=$NEW_IP,127.0.0.1,localhost \
        --service-cidr=10.96.0.0/12

    echo -e "${GREEN}  ✓ 인증서 재생성 완료${NC}"
}

# 컴포넌트 재시작
restart_components() {
    echo -e "${YELLOW}Kubernetes 컴포넌트 재시작 중...${NC}"

    # Static Pod 일시 중지 및 재시작
    if [ -d /etc/kubernetes/manifests ]; then
        echo "  - Static Pods 재시작"
        mv /etc/kubernetes/manifests /etc/kubernetes/manifests.tmp
        sleep 10
        mv /etc/kubernetes/manifests.tmp /etc/kubernetes/manifests
    fi

    # kubelet 재시작
    echo "  - kubelet 재시작"
    systemctl daemon-reload
    systemctl restart kubelet

    # 잠시 대기
    sleep 10

    echo -e "${GREEN}  ✓ 컴포넌트 재시작 완료${NC}"
}

# kube-proxy ConfigMap 업데이트
update_kube_proxy() {
    local OLD_IP=$1
    local NEW_IP=$2

    echo -e "${YELLOW}kube-proxy ConfigMap 업데이트 중...${NC}"

    # kubectl이 작동할 때까지 대기
    local count=0
    while ! kubectl get nodes &>/dev/null; do
        if [ $count -gt 30 ]; then
            echo -e "${RED}  ⚠ kubectl 연결 실패. 수동으로 업데이트 필요${NC}"
            return 1
        fi
        sleep 2
        count=$((count + 1))
    done

    # kube-proxy ConfigMap 수정
    kubectl -n kube-system get cm kube-proxy -o yaml | \
        sed "s/$OLD_IP/$NEW_IP/g" | \
        kubectl apply -f - 2>/dev/null && echo -e "${GREEN}  ✓ ConfigMap 업데이트 완료${NC}" || echo -e "${YELLOW}  ⚠ ConfigMap 업데이트 실패 (수동 확인 필요)${NC}"

    # kube-proxy 재시작
    kubectl -n kube-system rollout restart ds kube-proxy 2>/dev/null && echo -e "${GREEN}  ✓ kube-proxy 재시작${NC}" || echo -e "${YELLOW}  ⚠ kube-proxy 재시작 실패 (자동 복구됨)${NC}"
}

# 메인 실행
main() {
    # root 권한 확인
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}이 스크립트는 root 권한으로 실행해야 합니다.${NC}"
        exit 1
    fi

    # IP 감지 (첫 번째 인자로 IP 직접 지정 가능)
    NEW_IP=$(get_current_ip "$1")
    OLD_IP=$(get_old_ip)

    if [ -z "$NEW_IP" ]; then
        echo -e "${RED}현재 IP를 감지할 수 없습니다.${NC}"
        exit 1
    fi

    if [ -z "$OLD_IP" ]; then
        echo -e "${RED}기존 Kubernetes IP를 찾을 수 없습니다.${NC}"
        echo "새로운 클러스터인 것 같습니다."
        exit 1
    fi

    echo "IP 정보:"
    echo "  기존 IP: $OLD_IP"
    if [ -n "$1" ]; then
        echo "  새로운 IP: $NEW_IP (수동 지정)"
    else
        echo "  새로운 IP: $NEW_IP (자동 감지)"
    fi
    echo ""

    if [ "$OLD_IP" == "$NEW_IP" ]; then
        echo -e "${GREEN}IP가 변경되지 않았습니다. 종료합니다.${NC}"
        exit 0
    fi

    echo -e "${YELLOW}IP 변경을 시작합니다...${NC}"
    echo ""

    # 백업 생성
    echo "설정 백업 중..."
    tar czf /root/k8s_backup_$(date +%Y%m%d%H%M%S).tar.gz /etc/kubernetes /var/lib/kubelet 2>/dev/null
    echo -e "${GREEN}  ✓ 백업 완료${NC}"
    echo ""

    # IP 변경 실행
    change_ip "$OLD_IP" "$NEW_IP"
    echo ""

    # 사용자 kubeconfig도 업데이트
    if [ -f ~/.kube/config ]; then
        sed -i "s/$OLD_IP/$NEW_IP/g" ~/.kube/config
        echo -e "${GREEN}  ✓ 사용자 kubeconfig 업데이트${NC}"
    fi

    # 인증서 재생성
    regenerate_certs "$NEW_IP"
    echo ""

    # 컴포넌트 재시작
    restart_components
    echo ""

    # kube-proxy 업데이트 시도
    update_kube_proxy "$OLD_IP" "$NEW_IP"
    echo ""

    # 상태 확인
    echo -e "${YELLOW}시스템 상태 확인 중...${NC}"
    sleep 5

    # 노드 상태 확인
    if kubectl get nodes -o wide 2>/dev/null | grep -q "$NEW_IP"; then
        echo -e "${GREEN}✓ 노드 IP 변경 성공!${NC}"
    else
        echo -e "${YELLOW}⚠ 노드가 아직 준비 중입니다. 5-10분 후 확인하세요.${NC}"
    fi

    echo ""
    echo "======================================"
    echo -e "${GREEN}IP 변경 작업 완료!${NC}"
    echo "======================================"
    echo ""
    echo "확인 명령어:"
    echo "  kubectl get nodes -o wide"
    echo "  kubectl get pods -n kube-system"
    echo ""
    echo "참고: Flannel 네트워크가 준비되는데 5-10분 소요될 수 있습니다."
    echo "     Pod이 ContainerCreating 상태라면 잠시 기다려주세요."
}

# 스크립트 실행
main "$@"
