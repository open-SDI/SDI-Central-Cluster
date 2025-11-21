#!/bin/bash

#############################################
# Karmada v1.15.2 이미지 다운로드 스크립트
# 인터넷 연결 환경에서 실행
# Docker 또는 containerd 자동 감지
#############################################

set -e

KARMADA_VERSION="v1.15.2"
IMAGE_TAR="karmada-images-${KARMADA_VERSION}.tar"

echo "======================================"
echo "Karmada ${KARMADA_VERSION} 이미지 다운로드"
echo "======================================"

# 컨테이너 런타임 감지
if command -v docker &> /dev/null && systemctl is-active --quiet docker 2>/dev/null; then
    RUNTIME="docker"
    echo "컨테이너 런타임: Docker"
elif command -v ctr &> /dev/null; then
    RUNTIME="containerd"
    echo "컨테이너 런타임: containerd"
else
    echo "✗ Docker 또는 containerd를 찾을 수 없습니다."
    exit 1
fi
echo ""

# Karmada 이미지 목록
# karmadactl init --help에서 확인한 실제 이미지 경로 사용
# 참고: karmada-apiserver는 Kubernetes apiserver 이미지를 사용
#       karmada-kube-controller-manager는 Kubernetes controller-manager 이미지를 사용
KARMADA_IMAGES=(
    "registry.k8s.io/kube-apiserver:v1.31.3"  # karmada-apiserver가 사용
    "docker.io/karmada/karmada-controller-manager:${KARMADA_VERSION}"
    "docker.io/karmada/karmada-scheduler:${KARMADA_VERSION}"
    "docker.io/karmada/karmada-webhook:${KARMADA_VERSION}"
    "docker.io/karmada/karmada-aggregated-apiserver:${KARMADA_VERSION}"
    "registry.k8s.io/kube-controller-manager:v1.31.3"  # karmada-kube-controller-manager가 사용
    "docker.io/karmada/karmada-descheduler:${KARMADA_VERSION}"
    "docker.io/karmada/karmada-metrics-adapter:${KARMADA_VERSION}"
    "docker.io/karmada/karmada-search:${KARMADA_VERSION}"
    "quay.io/coreos/etcd:v3.5.9"
)

# 다운로드 성공한 이미지 목록
SUCCESSFUL_IMAGES=()
FAILED_IMAGES=()

echo "이미지 다운로드 중..."

for image in "${KARMADA_IMAGES[@]}"; do
    echo -n "  - ${image} ... "
    
    if [ "$RUNTIME" = "docker" ]; then
        if docker pull "${image}" >/dev/null 2>&1; then
            echo "✓ 성공"
            SUCCESSFUL_IMAGES+=("${image}")
        else
            echo "✗ 실패"
            FAILED_IMAGES+=("${image}")
        fi
    else
        # containerd 사용
        if ctr -n k8s.io images pull "${image}" >/dev/null 2>&1; then
            echo "✓ 성공"
            SUCCESSFUL_IMAGES+=("${image}")
        else
            echo "✗ 실패"
            FAILED_IMAGES+=("${image}")
        fi
    fi
done

if [ ${#FAILED_IMAGES[@]} -gt 0 ]; then
    echo ""
    echo "⚠ 일부 이미지 다운로드 실패:"
    for img in "${FAILED_IMAGES[@]}"; do
        echo "  - ${img}"
    done
    echo ""
    echo "다음 방법을 시도해보세요:"
    if [ "$RUNTIME" = "docker" ]; then
        echo "1. Docker Hub 로그인: docker login"
    else
        echo "1. containerd 네임스페이스 확인: ctr -n k8s.io images ls"
    fi
    echo "2. 네트워크 연결 확인"
    echo "3. 프록시 설정 확인 (필요시)"
    echo ""
    echo "계속 진행하시겠습니까? (성공한 이미지만 저장)"
    read -p "계속하려면 Enter를 누르세요 (중단: Ctrl+C): "
fi

if [ ${#SUCCESSFUL_IMAGES[@]} -eq 0 ]; then
    echo ""
    echo "✗ 다운로드 성공한 이미지가 없습니다."
    exit 1
fi

echo ""
echo "성공적으로 다운로드된 이미지: ${#SUCCESSFUL_IMAGES[@]}개"
echo ""
echo "이미지를 tar 파일로 저장 중..."

if [ "$RUNTIME" = "docker" ]; then
    docker save -o "${IMAGE_TAR}" "${SUCCESSFUL_IMAGES[@]}"
else
    # containerd 사용
    ctr -n k8s.io images export "${IMAGE_TAR}" "${SUCCESSFUL_IMAGES[@]}"
fi

# 파일 크기 확인
if [ -f "${IMAGE_TAR}" ]; then
    SIZE=$(du -h "${IMAGE_TAR}" | cut -f1)
    echo "✓ 이미지 저장 완료: ${IMAGE_TAR} (${SIZE})"
else
    echo "✗ 이미지 저장 실패"
    exit 1
fi

echo ""
echo "======================================"
echo "다운로드 완료!"
echo "======================================"
echo "다음 파일을 airgap 환경으로 전송하세요:"
echo "  - ${IMAGE_TAR}"
echo ""
echo "전송 예시:"
echo "  scp ${IMAGE_TAR} user@airgap-server:/path/to/destination/"
echo ""
echo "Airgap 환경에서 이미지 로드:"
echo "  ctr -n k8s.io images import ${IMAGE_TAR}"
