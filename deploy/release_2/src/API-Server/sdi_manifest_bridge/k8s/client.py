
import logging
from kubernetes import config, client
from kubernetes.client.exceptions import ApiException
import yaml

# 로거 설정
logger = logging.getLogger(__name__)

class K8sClient:
    """
    쿠버네티스 클러스터와의 통신을 관리합니다.
    서버 사이드 적용(Server-Side Apply)을 사용하여 리소스를 생성/업데이트합니다.
    """
    def __init__(self):
        try:
            # 클러스터 내부에서 실행될 때의 설정
            config.load_incluster_config()
        except config.ConfigException:
            # 로컬 환경에서 실행될 때 (개발용)
            config.load_kube_config()
        
        self.api_client = client.ApiClient()

    def apply(self, manifest: dict, dry_run: bool = False) -> dict:
        """
        Server-Side Apply 로 Pod을 생성/업데이트.
        - 존재하면 필드 병합, 없으면 생성
        - 여러 컨트롤러와 협업 안전 (managedFields)
        """
        api_version = manifest.get("apiVersion")
        kind = manifest.get("kind")
        meta = manifest.get("metadata", {}) or {}
        name = meta.get("name")
        namespace = meta.get("namespace") or "default"

        if api_version != "v1" or kind != "Pod" or not name:
            raise NotImplementedError("Only supports core/v1 Pod with metadata.name for now.")

        # SSA 핵심: PATCH + application/apply-patch+yaml
        path = f"/api/v1/namespaces/{namespace}/pods/{name}"
        query = [("fieldManager", "sdi-manifest-bridge"), ("force", "true")]
        if dry_run:
            query.append(("dryRun", "All"))

        headers = {"Content-Type": "application/apply-patch+yaml", "Accept": "application/json"}

        try:
            logger.info(f"Applying manifest for {kind}/{name} in namespace {namespace} (dry_run={dry_run})")
            # dict를 YAML 문자열로 변환
            yaml_body = yaml.dump(manifest)
            
            data, status, _ = self.api_client.call_api(
                path, "PATCH",
                path_params={},
                query_params=query,
                header_params=headers,
                body=yaml_body,
                auth_settings=["BearerToken"],
                response_type="object",
                _preload_content=True,
            )
            logger.info(f"Successfully applied manifest for {kind}/{name} (status={status})")
            return data
        except ApiException as e:
            try:
                error_body = yaml.safe_load(e.body) if e.body else {"message": e.reason}
            except Exception:
                error_body = {"message": e.reason, "raw": e.body}
            logger.error(f"Failed to apply manifest for {kind}/{name}: {error_body}")
            # http_resp 속성 제거
            raise ApiException(status=e.status, reason=e.reason, body=str(error_body))


# 싱글턴 인스턴스 생성
k8s_client = K8sClient()
