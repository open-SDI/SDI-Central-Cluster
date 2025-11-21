#!/bin/bash

#############################################
# Karmada 실제 사용 이미지 경로 확인 스크립트
# karmadactl init을 dry-run으로 실행하여 사용되는 이미지 확인
#############################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KARMADACTL="${SCRIPT_DIR}/../karmadactl"
KARMADA_VERSION="v1.15.2"

echo "======================================"
echo "Karmada ${KARMADA_VERSION} 이미지 경로 확인"
echo "======================================"

if [ ! -f "${KARMADACTL}" ]; then
    echo "오류: karmadactl을 찾을 수 없습니다: ${KARMADACTL}"
    exit 1
fi

echo ""
echo "방법 1: karmadactl init 도움말 확인"
echo "--------------------------------------"
"${KARMADACTL}" init --help | grep -A 5 "image\|registry" || true

echo ""
echo "방법 2: GitHub 릴리스 페이지에서 이미지 정보 확인"
echo "--------------------------------------"
echo "다음 URL에서 실제 이미지 경로를 확인하세요:"
echo "https://github.com/karmada-io/karmada/releases/tag/${KARMADA_VERSION}"
echo ""
echo "또는 Helm chart values 확인:"
echo "https://raw.githubusercontent.com/karmada-io/karmada/${KARMADA_VERSION}/charts/karmada/values.yaml"

echo ""
echo "방법 3: 실제 설치 후 이미지 경로 확인 (테스트 환경에서)"
echo "--------------------------------------"
echo "다음 명령어로 설치 후 사용된 이미지를 확인할 수 있습니다:"
echo "  kubectl get deployment -n karmada-system -o jsonpath='{.items[*].spec.template.spec.containers[*].image}'"
echo "  kubectl get statefulset -n karmada-system -o jsonpath='{.items[*].spec.template.spec.containers[*].image}'"

echo ""
echo "======================================"
echo "일반적인 Karmada 이미지 경로:"
echo "======================================"
echo "1. docker.io/karmada/karmada-*:${KARMADA_VERSION}"
echo "2. ghcr.io/karmada-io/karmada-*:${KARMADA_VERSION}"
echo "3. registry.k8s.io/karmada/karmada-*:${KARMADA_VERSION}"
echo ""
echo "etcd 이미지:"
echo "1. quay.io/coreos/etcd:v3.5.9"
echo "2. docker.io/library/etcd:3.5.9-0"
echo "3. registry.k8s.io/etcd:3.5.9-0"

