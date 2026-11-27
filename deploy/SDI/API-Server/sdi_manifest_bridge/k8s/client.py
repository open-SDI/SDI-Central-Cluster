
import logging
from kubernetes import config, client
from kubernetes.client.exceptions import ApiException
import yaml
import json
import os
import urllib3

from ..settings import k8s_pool_maxsize

# 로거 설정
logger = logging.getLogger(__name__)


# 모든 번들 리소스는 Karmada apiserver로 간다. MaleWorkload CRD도 Karmada에 설치되어
# 있고 male-operator가 Karmada를 감시한다 (호스트 클러스터의 CRD는 레거시).
# 호스트 클러스터로 보내야 하는 리소스가 생기면 여기에 kind를 추가.
HOST_ONLY_KINDS: set = set()
# 클러스터 범위 리소스(경로에 namespaces/<ns> 가 없음)
CLUSTER_SCOPED_KINDS = {"Namespace", "ClusterRole", "ClusterRoleBinding", "PriorityClass", "StorageClass",
                        "PersistentVolume", "CustomResourceDefinition", "ClusterPropagationPolicy",
                        "ClusterOverridePolicy"}

# 요청들이 스레드풀에서 동시에 apply 하므로(main.py) 연결 풀이 동시 호출 수보다 작으면
# urllib3 가 남는 연결을 버리고 매번 TLS 연결을 새로 맺는다. 클라이언트 기본값은 CPU 수 x 5.
# BRIDGE_K8S_POOL_MAXSIZE(기본 64, settings.py).
K8S_POOL_MAXSIZE = k8s_pool_maxsize()

# verify_ssl=False 는 의도한 설정이다. 호출마다 찍히던 InsecureRequestWarning 을 끈다.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _load_api_client(config_path: str, fallback_incluster: bool, label: str) -> client.ApiClient:
    """주어진 kubeconfig 경로(또는 in-cluster/default)로 별도의 ApiClient를 만든다."""
    try:
        if os.path.exists(config_path):
            configuration = client.Configuration()
            config.load_kube_config(config_file=config_path, client_configuration=configuration)
            logger.info(f"Successfully loaded {label} config from {config_path}")
        elif fallback_incluster:
            configuration = client.Configuration()
            try:
                config.load_incluster_config(client_configuration=configuration)
            except config.ConfigException:
                config.load_kube_config(client_configuration=configuration)
            logger.warning(f"{label} config not found at {config_path}. Using default config.")
        else:
            configuration = client.Configuration()
            config.load_kube_config(client_configuration=configuration)
            logger.warning(f"{label} config not found at {config_path}. Using default kube config.")
    except Exception as e:
        logger.error(f"Failed to load {label} K8s config: {e}")
        configuration = client.Configuration()

    configuration.verify_ssl = False
    configuration.connection_pool_maxsize = max(configuration.connection_pool_maxsize or 0, K8S_POOL_MAXSIZE)
    return client.ApiClient(configuration)


class K8sClient:
    """
    번들 경로(/v1/render-bundle · /v1/apply-bundle)의 쿠버네티스 클라이언트.
    (예전 단순 입력 경로 /v1/apply 는 core/legacy_client.py 의 SDIClient 를 쓴다.)
    서버 사이드 적용(Server-Side Apply)을 사용하여 리소스를 생성/업데이트합니다.

    Karmada(멀티클러스터 전파 대상)와 호스트 클러스터(MaleWorkload 등 센트럴 전용
    리소스)에 각각 별도의 ApiClient로 연결하고, 리소스 kind에 따라 적절한 쪽으로 보낸다.
    """

    def __init__(self):
        self.karmada_api_client = _load_api_client(
            "/etc/karmada/karmada-apiserver.config", fallback_incluster=True, label="Karmada")
        self.host_api_client = _load_api_client(
            "/root/.kube/config", fallback_incluster=True, label="Host cluster")

    def apply(self, manifest: dict, dry_run: bool = False) -> dict:
        """
        Server-Side Apply를 사용하여 리소스를 생성/업데이트합니다.
        apiVersion과 kind를 분석하여 적절한 API 경로를 동적으로 생성합니다.
        """
        api_version = manifest.get("apiVersion")
        kind = manifest.get("kind")
        meta = manifest.get("metadata", {}) or {}
        name = meta.get("name")
        namespace = meta.get("namespace") or "default"

        if not api_version or not kind or not name:
            raise ValueError("Resource manifest must contain apiVersion, kind, and metadata.name")

        api_client = self.host_api_client if kind in HOST_ONLY_KINDS else self.karmada_api_client

        # 리소스 종류에 따른 복수형 이름(Plural) 결정
        plural_mapping = {
            "Deployment": "deployments",
            "MaleWorkload": "maleworkloads",
            "Pod": "pods",
            "Service": "services",
            "StatefulSet": "statefulsets",
            "Job": "jobs"
        }
        plural = plural_mapping.get(kind, kind.lower() + ("es" if kind.lower().endswith("s") else "s"))  # PriorityClass → priorityclasses
        if plural.endswith("ys"): # e.g. Policy -> Policies (예외 처리용)
            plural = plural[:-2] + "ies"

        # API 경로 생성. 클러스터 범위 리소스(Namespace 등)는 namespaces/<ns> 구간이 없음
        ns_part = "" if kind in CLUSTER_SCOPED_KINDS else f"namespaces/{namespace}/"
        if "/" in api_version:
            # 커스텀 리소스 (e.g., apps/v1, opensdi.opensdi.io/v1alpha1)
            group, version = api_version.split("/")
            path = f"/apis/{group}/{version}/{ns_part}{plural}/{name}"
        else:
            # 코어 리소스 (e.g., v1)
            path = f"/api/{api_version}/{ns_part}{plural}/{name}"

        # SSA 설정: PATCH + application/apply-patch+yaml
        query = [("fieldManager", "sdi-manifest-bridge"), ("force", "true")]
        if dry_run:
            query.append(("dryRun", "All"))

        headers = {
            "Content-Type": "application/apply-patch+yaml",
            "Accept": "application/json"
        }

        try:
            target = "host cluster" if kind in HOST_ONLY_KINDS else "Karmada"
            logger.info(f"Applying {kind}/{name} in {namespace} (dry_run={dry_run}) via {path} [{target}]")

            data, status, _ = api_client.call_api(
                path, "PATCH",
                path_params={},
                query_params=query,
                header_params=headers,
                # apply-patch+yaml 은 JSON 아닌 content-type 이라 클라이언트가 dict 를 직렬화하지
                # 않는다(문자열/바이트만 통과). JSON 은 YAML 의 부분집합이므로 직렬화해서 보낸다.
                body=json.dumps(manifest),
                auth_settings=["BearerToken"],
                response_type="object",
                _preload_content=True,
            )
            logger.info(f"Successfully applied {kind}/{name} (status={status})")
            return data
        except ApiException as e:
            logger.error(f"Failed to apply {kind}/{name}: {e.body if hasattr(e, 'body') else e}")
            raise e


# 싱글턴 인스턴스 생성
k8s_client = K8sClient()
