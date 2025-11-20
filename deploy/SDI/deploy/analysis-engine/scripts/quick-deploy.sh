#!/bin/bash

# SDI Analysis Engine 빠른 배포 스크립트
# 기존 이미지를 사용하여 빠르게 배포

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 설정
APP_NAME="sdi-analysis-engine"
NAMESPACE="default"
DEPLOYMENT_FILE="/root/SDI/deploy/analysis-engine/manifests/sdi-analysis-engine.yaml"

# 로그 함수
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_header() {
    echo -e "${CYAN}=== $1 ===${NC}"
}

# 빠른 배포
function quick_deploy() {
    log_header "SDI Analysis Engine 빠른 배포"
    
    # 기존 배포 삭제
    log_info "기존 배포 삭제 중..."
    kubectl delete -f $DEPLOYMENT_FILE --ignore-not-found=true
    
    # 잠시 대기
    log_info "삭제 완료 대기 중..."
    sleep 3
    
    # 새 배포 생성
    log_info "새 배포 생성 중..."
    kubectl apply -f $DEPLOYMENT_FILE
    
    # 파드 준비 대기
    log_info "파드 준비 대기 중..."
    kubectl wait --for=condition=ready pod -l app=$APP_NAME --timeout=60s
    
    log_success "빠른 배포 완료!"
    
    # 상태 표시
    echo ""
    log_info "배포 상태:"
    kubectl get pods -l app=$APP_NAME -o wide
    echo ""
    log_info "서비스 상태:"
    kubectl get svc -l app=$APP_NAME
    echo ""
    log_info "접속 정보:"
    echo "  - REST API: http://localhost:30050"
    echo "  - gRPC: localhost:30051"
    echo "  - 포트 포워딩: kubectl port-forward <pod-name> 50051:50051"
}

# 메인 실행
quick_deploy
