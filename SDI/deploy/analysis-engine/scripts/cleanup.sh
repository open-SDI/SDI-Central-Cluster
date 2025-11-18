#!/bin/bash

# SDI Analysis Engine 정리 스크립트
# 모든 리소스를 안전하게 삭제

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

# 확인 프롬프트
confirm() {
    local message="$1"
    local default="${2:-n}"
    
    if [[ "$default" == "y" ]]; then
        read -p "$message (Y/n): " -r
    else
        read -p "$message (y/N): " -r
    fi
    
    case $REPLY in
        [yY]|[yY][eE][sS]) return 0 ;;
        *) return 1 ;;
    esac
}

# 전체 정리
function cleanup_all() {
    log_header "SDI Analysis Engine 전체 정리"
    
    if confirm "모든 SDI Analysis Engine 리소스를 삭제하시겠습니까?"; then
        # Deployment, Service, ConfigMap, Secret 삭제
        log_info "리소스 삭제 중..."
        kubectl delete -f $DEPLOYMENT_FILE --ignore-not-found=true
        
        # 추가 정리 (라벨로 찾아서 삭제)
        log_info "라벨 기반 추가 정리 중..."
        kubectl delete pods -l app=$APP_NAME --ignore-not-found=true
        kubectl delete services -l app=$APP_NAME --ignore-not-found=true
        kubectl delete configmaps -l app=$APP_NAME --ignore-not-found=true
        kubectl delete secrets -l app=$APP_NAME --ignore-not-found=true
        
        log_success "전체 정리 완료!"
    else
        log_info "정리를 취소했습니다."
    fi
}

# 파드만 정리
function cleanup_pods() {
    log_header "파드만 정리"
    
    if confirm "SDI Analysis Engine 파드만 삭제하시겠습니까?"; then
        log_info "파드 삭제 중..."
        kubectl delete pods -l app=$APP_NAME --ignore-not-found=true
        log_success "파드 정리 완료!"
    else
        log_info "정리를 취소했습니다."
    fi
}

# 서비스만 정리
function cleanup_services() {
    log_header "서비스만 정리"
    
    if confirm "SDI Analysis Engine 서비스를 삭제하시겠습니까?"; then
        log_info "서비스 삭제 중..."
        kubectl delete services -l app=$APP_NAME --ignore-not-found=true
        log_success "서비스 정리 완료!"
    else
        log_info "정리를 취소했습니다."
    fi
}

# 설정만 정리
function cleanup_configs() {
    log_header "설정만 정리"
    
    if confirm "ConfigMap과 Secret을 삭제하시겠습니까?"; then
        log_info "ConfigMap 삭제 중..."
        kubectl delete configmap influxdb-config --ignore-not-found=true
        log_info "Secret 삭제 중..."
        kubectl delete secret influxdb-token --ignore-not-found=true
        log_success "설정 정리 완료!"
    else
        log_info "정리를 취소했습니다."
    fi
}

# 상태 확인
function check_status() {
    log_header "현재 상태 확인"
    
    log_info "파드 상태:"
    kubectl get pods -l app=$APP_NAME 2>/dev/null || log_warning "파드가 없습니다."
    
    echo ""
    log_info "서비스 상태:"
    kubectl get svc -l app=$APP_NAME 2>/dev/null || log_warning "서비스가 없습니다."
    
    echo ""
    log_info "ConfigMap 상태:"
    kubectl get configmap influxdb-config 2>/dev/null || log_warning "ConfigMap이 없습니다."
    
    echo ""
    log_info "Secret 상태:"
    kubectl get secret influxdb-token 2>/dev/null || log_warning "Secret이 없습니다."
}

# 도움말 표시
function show_help() {
    cat << EOF
SDI Analysis Engine 정리 스크립트

사용법: $0 [옵션]

옵션:
  --all           모든 리소스 정리 (기본값)
  --pods-only     파드만 정리
  --services-only 서비스만 정리
  --configs-only  설정만 정리 (ConfigMap, Secret)
  --status        현재 상태 확인
  --help          이 도움말 표시

예시:
  $0                    # 모든 리소스 정리
  $0 --pods-only        # 파드만 정리
  $0 --services-only    # 서비스만 정리
  $0 --configs-only     # 설정만 정리
  $0 --status          # 현재 상태 확인

주의:
  - 이 스크립트는 SDI Analysis Engine 관련 리소스를 정리합니다.
  - 정리 전에 중요한 데이터를 백업하세요.
  - 정리 후에는 서비스가 중단됩니다.

EOF
}

# 메인 실행
case "${1:-all}" in
    --all)
        cleanup_all
        ;;
    --pods-only)
        cleanup_pods
        ;;
    --services-only)
        cleanup_services
        ;;
    --configs-only)
        cleanup_configs
        ;;
    --status)
        check_status
        ;;
    --help)
        show_help
        exit 0
        ;;
    *)
        log_error "알 수 없는 옵션: $1"
        show_help
        exit 1
        ;;
esac

echo ""
check_status
