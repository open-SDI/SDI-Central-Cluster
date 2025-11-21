#!/bin/bash

#############################################
# Karmada v1.15.2 CRD 다운로드 스크립트
# 인터넷 연결 환경에서 실행
#############################################

set -e

KARMADA_VERSION="v1.15.2"
CRD_URL="https://github.com/karmada-io/karmada/releases/download/${KARMADA_VERSION}/crds.tar.gz"
CRD_FILE="karmada-crds-${KARMADA_VERSION}.tar.gz"

echo "======================================"
echo "Karmada ${KARMADA_VERSION} CRD 다운로드"
echo "======================================"

echo "CRD 파일 다운로드 중..."
curl -L -o "${CRD_FILE}" "${CRD_URL}"

if [ -f "${CRD_FILE}" ]; then
    SIZE=$(du -h "${CRD_FILE}" | cut -f1)
    echo "✓ CRD 다운로드 완료: ${CRD_FILE} (${SIZE})"
    
    # 압축 해제하여 내용 확인
    echo ""
    echo "CRD 파일 목록:"
    tar -tzf "${CRD_FILE}" | head -10
    echo "..."
else
    echo "✗ CRD 다운로드 실패"
    exit 1
fi

echo ""
echo "======================================"
echo "다운로드 완료!"
echo "======================================"
echo "다음 파일을 airgap 환경으로 전송하세요:"
echo "  - ${CRD_FILE}"
echo ""
echo "전송 예시:"
echo "  scp ${CRD_FILE} user@airgap-server:/path/to/destination/"

