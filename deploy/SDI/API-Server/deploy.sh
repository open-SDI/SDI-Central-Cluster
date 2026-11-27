#!/bin/bash

# 이 스크립트는 SDI Manifest Bridge 애플리케이션을 쿠버네티스 클러스터에 배포합니다.
# 스크립트가 위치한 디렉토리 기준으로 kubernetes_manifests 경로를 사용합니다.

set -e  # 오류 발생 시 스크립트 중단

BASE_DIR=$(dirname "$0")
MANIFEST_DIR="${BASE_DIR}/kubernetes_manifests"

# 1. 네임스페이스 생성
echo "Applying 00-namespace.yaml..."
kubectl apply -f "${MANIFEST_DIR}/00-namespace.yaml"

# 2. RBAC (ServiceAccount, Role, RoleBinding) 생성
echo "Applying 01-rbac.yaml..."
kubectl apply -f "${MANIFEST_DIR}/01-rbac.yaml"

# 3. 컨피그맵 생성
echo "Applying 02-configmap.yaml..."
kubectl apply -f "${MANIFEST_DIR}/02-configmap.yaml"

# 4. 디플로이먼트 생성
echo "Applying 03-deployment.yaml..."
kubectl apply -f "${MANIFEST_DIR}/03-deployment.yaml"

# 5. 서비스 생성
echo "Applying 04-service.yaml..."
kubectl apply -f "${MANIFEST_DIR}/04-service.yaml"

# 6. Karmada 리소스 해석기 설정(Service 등 부속 리소스가 Deployment 를 따라가게 함). Karmada API 서버에 적용
KARMADA_KUBECONFIG="${KARMADA_KUBECONFIG:-/etc/karmada/karmada-apiserver.config}"
if [ -f "${KARMADA_KUBECONFIG}" ]; then
  echo "Applying karmada_manifests/sdi-deployment-dependencies.yaml (Karmada)..."
  kubectl --kubeconfig "${KARMADA_KUBECONFIG}" apply -f "${BASE_DIR}/karmada_manifests/sdi-deployment-dependencies.yaml"
else
  echo "KARMADA_KUBECONFIG(${KARMADA_KUBECONFIG}) 없음: karmada_manifests/ 는 Karmada API 서버에 따로 적용하세요"
fi

echo -e "\nDeployment complete. All resources have been applied to the 'sdi-manifest-bridge' namespace."
echo "To check the status of the deployment, run: kubectl get all -n sdi-manifest-bridge"
