#!/bin/bash

# SDI Analysis Engine Kubernetes 배포 스크립트
# 사용법: ./deploy.sh [deploy|delete|restart|logs|status|build|exec|port-forward]

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
DOCKER_REGISTRY="ketidevit2"
IMAGE_BASE="sdi-analysis-engine"
VERSION="v0.1.8"
IMAGE_NAME="${DOCKER_REGISTRY}/${IMAGE_BASE}:${VERSION}"
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

# 도움말 표시
function usage() {
    echo "SDI Analysis Engine Kubernetes 배포 스크립트"
    echo ""
    echo "사용법: $0 [명령어]"
    echo ""
    echo "현재 설정:"
    echo "  이미지: $IMAGE_NAME"
    echo "  배포 파일: $DEPLOYMENT_FILE"
    echo "  네임스페이스: $NAMESPACE"
    echo ""
    echo "명령어:"
    echo "  deploy         - 파드 배포 (kubectl apply만)"
    echo "  full-deploy    - 전체 배포 (빌드 + 푸시 + 버전업데이트 + 배포)"
    echo "  delete         - 파드 삭제"
    echo "  restart        - 파드 재시작"
    echo "  logs           - 파드 로그 확인 (실시간)"
    echo "  status         - 파드 상태 확인"
    echo "  build          - 도커 이미지만 빌드"
    echo "  push           - 도커 이미지 푸시 (빌드 포함)"
    echo "  update-version - YAML 파일의 이미지 버전 업데이트"
    echo "  exec           - 파드에 접속"
    echo "  port-forward   - 로컬 포트 포워딩 (50051:50051)"
    echo "  describe       - 파드 상세 정보"
    echo "  health-check   - 헬스체크 (REST API)"
    echo "  grpc-test      - gRPC 연결 테스트"
    echo ""
    echo "서비스 접속 정보:"
    echo "  - REST API: http://localhost:30050"
    echo "  - gRPC: localhost:30051"
    echo "  - 포트 포워딩: $0 port-forward"
}

# Docker 이미지 빌드
function build_image() {
    log_header "Docker 이미지 빌드"
    log_info "이미지: $IMAGE_NAME"
    
    # 기존 이미지 삭제 (있다면)
    log_info "기존 이미지 삭제 중..."
    docker rmi -f $IMAGE_NAME 2>/dev/null || true
    
    # 빌드 캐시 정리
    log_info "빌드 캐시 정리 중..."
    docker builder prune -f
    
    # 캐시 없이 빌드
    log_info "캐시 없이 새로 빌드 중..."
    cd /root/SDI/analysis-engine
    docker build --no-cache --pull -t $IMAGE_NAME .
    
    log_success "이미지 빌드 완료: $IMAGE_NAME"
}

# Docker 이미지 푸시
function push_image() {
    log_header "Docker 이미지 푸시"
    
    # 먼저 빌드
    build_image
    
    # Docker Hub에 푸시
    log_info "Docker Hub에 이미지 푸시 중..."
    log_info "이미지: $IMAGE_NAME"
    docker push $IMAGE_NAME
    
    log_success "이미지 푸시 완료!"
}

# YAML 파일 버전 업데이트
function update_yaml_version() {
    log_header "YAML 파일 버전 업데이트"
    log_info "파일: $DEPLOYMENT_FILE"
    log_info "이미지: $IMAGE_NAME"
    
    if [ ! -f "$DEPLOYMENT_FILE" ]; then
        log_error "배포 파일을 찾을 수 없습니다: $DEPLOYMENT_FILE"
        exit 1
    fi
    
    # sed를 사용해서 이미지 버전 업데이트
    sed -i.bak "s|image: ${DOCKER_REGISTRY}/${IMAGE_BASE}:.*|image: ${IMAGE_NAME}|g" $DEPLOYMENT_FILE
    
    log_success "YAML 파일 업데이트 완료!"
    log_info "백업 파일: ${DEPLOYMENT_FILE}.bak"
    
    # 변경사항 확인
    log_info "변경된 이미지 정보:"
    grep "image: ${DOCKER_REGISTRY}/${IMAGE_BASE}" $DEPLOYMENT_FILE || log_warning "이미지 라인을 찾을 수 없습니다."
}

# 전체 배포
function full_deploy() {
    log_header "SDI Analysis Engine 전체 배포"
    log_info "버전: $VERSION"
    log_info "이미지: $IMAGE_NAME"
    echo ""
    
    # 0. 캐시 완전 정리
    log_info "0단계: 캐시 및 기존 리소스 정리"
    log_info "Docker 시스템 정리 중..."
    docker system prune -af || true
    log_info "기존 이미지 삭제 중..."
    docker rmi -f $IMAGE_NAME 2>/dev/null || true
    echo ""
    
    # 1. Docker 이미지 빌드 및 푸시
    log_info "1단계: Docker 이미지 빌드 & 푸시"
    push_image
    echo ""
    
    # 2. YAML 파일 버전 업데이트
    log_info "2단계: YAML 파일 버전 업데이트"
    update_yaml_version
    echo ""
    
    # 3. Kubernetes 배포
    log_info "3단계: Kubernetes 배포"
    deploy_pod
    
    echo ""
    log_success "전체 배포 완료!"
    log_info "이미지: $IMAGE_NAME"
    log_info "배포 파일: $DEPLOYMENT_FILE"
}

# 파드 배포
function deploy_pod() {
    log_header "Kubernetes 파드 배포"
    log_info "배포 파일: $DEPLOYMENT_FILE"
    
    # 배포 파일 존재 확인
    if [ ! -f "$DEPLOYMENT_FILE" ]; then
        log_error "배포 파일을 찾을 수 없습니다: $DEPLOYMENT_FILE"
        exit 1
    fi
    
    # 기존 배포 삭제 (있다면)
    log_info "기존 리소스 정리 중..."
    kubectl delete -f $DEPLOYMENT_FILE --ignore-not-found=true
    log_info "기존 리소스 정리 대기 중..."
    sleep 5
    
    # 새 배포 생성
    log_info "새 리소스 배포 중..."
    kubectl apply -f $DEPLOYMENT_FILE
    
    log_info "파드 시작 대기 중..."
    kubectl wait --for=condition=ready pod -l app=$APP_NAME --timeout=120s
    
    log_success "파드 배포 완료!"
    echo ""
    show_status
    echo ""
    log_info "서비스 접속 정보:"
    echo "  - REST API: http://localhost:30050"
    echo "  - gRPC: localhost:30051"
    echo "  - 포트 포워딩: $0 port-forward"
}

# 파드 삭제
function delete_pod() {
    log_header "SDI Analysis Engine 파드 삭제"
    kubectl delete -f $DEPLOYMENT_FILE --ignore-not-found=true
    log_success "파드 삭제 완료!"
}

# 파드 재시작
function restart_pod() {
    log_header "SDI Analysis Engine 파드 재시작"
    
    # 기존 파드 완전 삭제
    log_info "기존 파드 삭제 중..."
    kubectl delete -f $DEPLOYMENT_FILE --ignore-not-found=true
    
    # 잠시 대기
    log_info "파드 삭제 대기 중..."
    sleep 10
    
    # 새로 배포
    log_info "새 파드 배포 중..."
    kubectl apply -f $DEPLOYMENT_FILE
    
    # 파드 준비 대기
    log_info "파드 준비 대기 중..."
    kubectl wait --for=condition=ready pod -l app=$APP_NAME --timeout=120s
    
    log_success "파드 재시작 완료!"
}

# 파드 로그 확인
function show_logs() {
    log_header "파드 로그 (실시간)"
    log_info "Ctrl+C로 종료"
    echo ""
    kubectl logs -f -l app=$APP_NAME -n $NAMESPACE --tail=50
}

# 파드 상태 확인
function show_status() {
    log_header "파드 상태"
    kubectl get pods -l app=$APP_NAME -n $NAMESPACE -o wide
    echo ""
    log_info "서비스 상태:"
    kubectl get svc -l app=$APP_NAME -n $NAMESPACE
    echo ""
    log_info "배포 상태:"
    kubectl get deployment $APP_NAME -n $NAMESPACE
}

# 파드 접속
function exec_pod() {
    POD_NAME=$(kubectl get pods -l app=$APP_NAME -n $NAMESPACE -o jsonpath='{.items[0].metadata.name}')
    if [ -z "$POD_NAME" ]; then
        log_error "실행 중인 파드를 찾을 수 없습니다."
        exit 1
    fi
    
    log_info "파드에 접속 중: $POD_NAME"
    kubectl exec -it $POD_NAME -n $NAMESPACE -- /bin/bash
}

# 포트 포워딩
function port_forward() {
    POD_NAME=$(kubectl get pods -l app=$APP_NAME -n $NAMESPACE -o jsonpath='{.items[0].metadata.name}')
    if [ -z "$POD_NAME" ]; then
        log_error "실행 중인 파드를 찾을 수 없습니다."
        exit 1
    fi
    
    log_info "포트 포워딩 시작: localhost:50051 -> $POD_NAME:50051"
    log_info "Ctrl+C로 종료"
    kubectl port-forward $POD_NAME 50051:50051 -n $NAMESPACE
}

# 파드 상세 정보
function describe_pod() {
    POD_NAME=$(kubectl get pods -l app=$APP_NAME -n $NAMESPACE -o jsonpath='{.items[0].metadata.name}')
    if [ -z "$POD_NAME" ]; then
        log_error "실행 중인 파드를 찾을 수 없습니다."
        exit 1
    fi
    
    log_info "파드 상세 정보: $POD_NAME"
    kubectl describe pod $POD_NAME -n $NAMESPACE
}

# 헬스체크
function health_check() {
    log_header "헬스체크 (REST API)"
    
    # 파드가 실행 중인지 확인
    POD_NAME=$(kubectl get pods -l app=$APP_NAME -n $NAMESPACE -o jsonpath='{.items[0].metadata.name}')
    if [ -z "$POD_NAME" ]; then
        log_error "실행 중인 파드를 찾을 수 없습니다."
        exit 1
    fi
    
    # 포트 포워딩으로 헬스체크
    log_info "포트 포워딩으로 헬스체크 중..."
    kubectl port-forward $POD_NAME 5000:5000 -n $NAMESPACE &
    PORT_FORWARD_PID=$!
    
    # 포트 포워딩 시작 대기
    sleep 3
    
    # 헬스체크 실행
    log_info "REST API 헬스체크 실행 중..."
    if curl -s http://localhost:5000/health > /dev/null; then
        log_success "헬스체크 성공!"
        curl -s http://localhost:5000/health | jq . 2>/dev/null || curl -s http://localhost:5000/health
    else
        log_error "헬스체크 실패!"
    fi
    
    # 포트 포워딩 종료
    kill $PORT_FORWARD_PID 2>/dev/null || true
}

# gRPC 테스트
function grpc_test() {
    log_header "gRPC 연결 테스트"
    
    # 파드가 실행 중인지 확인
    POD_NAME=$(kubectl get pods -l app=$APP_NAME -n $NAMESPACE -o jsonpath='{.items[0].metadata.name}')
    if [ -z "$POD_NAME" ]; then
        log_error "실행 중인 파드를 찾을 수 없습니다."
        exit 1
    fi
    
    log_info "gRPC 포트 포워딩 중..."
    kubectl port-forward $POD_NAME 50051:50051 -n $NAMESPACE &
    PORT_FORWARD_PID=$!
    
    # 포트 포워딩 시작 대기
    sleep 3
    
    # gRPC 연결 테스트
    log_info "gRPC 연결 테스트 실행 중..."
    if command -v grpcurl &> /dev/null; then
        if grpcurl -plaintext localhost:50051 list; then
            log_success "gRPC 연결 성공!"
        else
            log_error "gRPC 연결 실패!"
        fi
    else
        log_warning "grpcurl이 설치되지 않았습니다. gRPC 테스트를 건너뜁니다."
        log_info "grpcurl 설치: apt-get install grpcurl 또는 go install github.com/fullstorydev/grpcurl/cmd/grpcurl@latest"
    fi
    
    # 포트 포워딩 종료
    kill $PORT_FORWARD_PID 2>/dev/null || true
}

# kubectl 설치 확인
if ! command -v kubectl &> /dev/null; then
    log_error "kubectl이 설치되어 있지 않습니다."
    log_info "쿠버네티스 클러스터에 접근하려면 kubectl이 필요합니다."
    exit 1
fi

# 쿠버네티스 클러스터 연결 확인
if ! kubectl cluster-info &> /dev/null; then
    log_error "쿠버네티스 클러스터에 연결할 수 없습니다."
    log_info "kubectl config를 확인해주세요."
    exit 1
fi

# 메인 실행
case "${1:-deploy}" in
    deploy)
        deploy_pod
        ;;
    full-deploy)
        full_deploy
        ;;
    delete)
        delete_pod
        ;;
    restart)
        restart_pod
        ;;
    logs)
        show_logs
        ;;
    status)
        show_status
        ;;
    build)
        build_image
        ;;
    push)
        push_image
        ;;
    update-version)
        update_yaml_version
        ;;
    exec)
        exec_pod
        ;;
    port-forward)
        port_forward
        ;;
    describe)
        describe_pod
        ;;
    health-check)
        health_check
        ;;
    grpc-test)
        grpc_test
        ;;
    *)
        usage
        exit 1
        ;;
esac
