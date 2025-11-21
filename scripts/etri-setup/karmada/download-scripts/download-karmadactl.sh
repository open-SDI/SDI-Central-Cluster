#!/bin/bash
# karmadactl 바이너리 다운로드 스크립트
# 인터넷 연결 환경에서 실행

set -e

KARMADA_VERSION="v1.15.2"
BINARY_NAME="karmadactl-linux-amd64.tgz"
DOWNLOAD_URL="https://github.com/karmada-io/karmada/releases/download/${KARMADA_VERSION}/${BINARY_NAME}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "${SCRIPT_DIR}")"

echo "======================================"
echo "karmadactl ${KARMADA_VERSION} 다운로드"
echo "======================================"
echo ""

# 1. 다운로드
echo "1. karmadactl 바이너리 다운로드 중..."
echo "URL: ${DOWNLOAD_URL}"

cd "${PARENT_DIR}"
curl -L "${DOWNLOAD_URL}" -o "${BINARY_NAME}"

if [ ! -f "${BINARY_NAME}" ]; then
    echo "✗ 다운로드 실패"
    exit 1
fi

# 파일 타입 확인
FILE_TYPE=$(file "${BINARY_NAME}" | grep -o "gzip compressed data" || echo "")
if [ -z "$FILE_TYPE" ]; then
    echo "✗ 다운로드한 파일이 올바른 형식이 아닙니다."
    cat "${BINARY_NAME}"
    exit 1
fi

echo "✓ 다운로드 완료: ${BINARY_NAME}"
echo ""

# 2. 압축 해제
echo "2. 압축 해제 중..."
tar -xzf "${BINARY_NAME}"

if [ ! -f "karmadactl" ]; then
    echo "✗ 압축 해제 실패"
    exit 1
fi

chmod +x karmadactl
echo "✓ 압축 해제 완료"
echo ""

# 3. 버전 확인
echo "3. 버전 확인..."
./karmadactl version

echo ""
echo "======================================"
echo "다운로드 완료!"
echo "======================================"
echo ""
echo "다운로드된 파일:"
echo "  - ${PARENT_DIR}/karmadactl"
echo "  - ${PARENT_DIR}/${BINARY_NAME}"
echo ""
echo "다음 단계:"
echo "  cd ${PARENT_DIR}"
echo "  ./install-karmada.sh"

