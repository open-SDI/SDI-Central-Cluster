#!/bin/bash

set -e

# --- 변수 설정 ---
NEW_IMAGE=$1
DEPLOY_YAML="sdi-cluster-scheduler-deploy.yaml"
NAMESPACE="sdi-system"
SECRET_NAME="sdi-karmada-kubeconfig"
SOURCE_KUBECONFIG="/etc/karmada/karmada-apiserver.config"

# --- 스크립트 시작 ---

# 1. 필요 파일 및 인자 확인
if [ -z "$NEW_IMAGE" ]; then
  echo "❌ 오류: 배포할 도커 이미지 태그를 입력해야 합니다."
  echo "   사용법: $0 [이미지 주소:태그]"
  exit 1
fi
if [ ! -f "$DEPLOY_YAML" ]; then
  echo "❌ 오류: 배포 템플릿 파일 '$DEPLOY_YAML'을 찾을 수 없습니다."
  exit 1
fi

echo "🚀 SDI 스케줄러 통합 배포 V2를 시작합니다..."
echo "   - 대상 이미지: $NEW_IMAGE"

# 2. Namespace, RBAC 등 기본 리소스 적용
echo "📜 기본 리소스를 적용합니다..."
kubectl apply -f $DEPLOY_YAML

# 3. [개선된 방법] 호스트의 kubeconfig에서 인증서 데이터만 추출
echo "🔑 호스트 kubeconfig에서 인증서 데이터를 추출합니다..."
CA_DATA=$(sudo grep 'certificate-authority-data:' $SOURCE_KUBECONFIG | awk '{print $2}')
CLIENT_CERT_DATA=$(sudo grep 'client-certificate-data:' $SOURCE_KUBECONFIG | awk '{print $2}')
CLIENT_KEY_DATA=$(sudo grep 'client-key-data:' $SOURCE_KUBECONFIG | awk '{print $2}')

if [ -z "$CA_DATA" ] || [ -z "$CLIENT_CERT_DATA" ] || [ -z "$CLIENT_KEY_DATA" ]; then
    echo "❌ 오류: 호스트 kubeconfig '$SOURCE_KUBECONFIG'에서 인증서 정보를 추출하지 못했습니다."
    exit 1
fi

# 4. [개선된 방법] 추출된 데이터와 올바른 서버 주소로 완벽한 kubeconfig를 새로 조립
echo "✏️ 올바른 kubeconfig 내용을 새로 조립합니다..."
TEMP_KUBECONFIG_FILE="temp-kubeconfig-final.yaml"
KARMADA_SERVER_URL="https://karmada-apiserver.karmada-system.svc:5443"

cat <<EOF > $TEMP_KUBECONFIG_FILE
apiVersion: v1
kind: Config
clusters:
- name: karmada-apiserver
  cluster:
    server: $KARMADA_SERVER_URL
    certificate-authority-data: $CA_DATA
contexts:
- name: karmada-apiserver
  context:
    cluster: karmada-apiserver
    user: karmada-admin
users:
- name: karmada-admin
  user:
    client-certificate-data: $CLIENT_CERT_DATA
    client-key-data: $CLIENT_KEY_DATA
current-context: karmada-apiserver
EOF
echo "   - 완벽한 임시 kubeconfig 파일 생성 완료."

# 5. 조립된 kubeconfig로 Secret 재생성
echo "🔒 새로운 kubeconfig로 Secret을 재생성합니다..."
kubectl delete secret $SECRET_NAME -n $NAMESPACE --ignore-not-found=true
kubectl create secret generic $SECRET_NAME -n $NAMESPACE --from-file=kubeconfig=./$TEMP_KUBECONFIG_FILE
echo "   - Secret '$SECRET_NAME' 생성 완료."

# 6. Deployment 이미지 태그 교체 및 배포
echo "🔄 배포 파일의 이미지를 '$NEW_IMAGE'(으)로 교체 후 배포합니다..."
TEMP_DEPLOY_YAML="temp-final-deploy.yaml"
sed "s|image: .*|image: $NEW_IMAGE|g" $DEPLOY_YAML > $TEMP_DEPLOY_YAML
kubectl apply -f $TEMP_DEPLOY_YAML
echo "   - 배포(업데이트) 요청 완료."

# 7. 배포 완료 대기
echo "⏳ 배포가 완료될 때까지 대기합니다..."
kubectl rollout status deployment/sdi-cluster-scheduler -n $NAMESPACE

# 8. 임시 파일 삭제
echo "🧹 임시 파일들을 삭제합니다..."
rm $TEMP_KUBECONFIG_FILE
rm $TEMP_DEPLOY_YAML

echo "✅ 성공: SDI 스케줄러 배포가 성공적으로 완료되었습니다!"