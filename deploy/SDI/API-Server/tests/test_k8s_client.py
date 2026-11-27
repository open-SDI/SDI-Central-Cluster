"""K8sClient.apply 요청 구성 테스트 (클러스터 불필요)."""
import json
from unittest.mock import MagicMock

from sdi_manifest_bridge.k8s.client import K8sClient


def _client_with_mock():
    c = K8sClient.__new__(K8sClient)  # __init__(kubeconfig 로드) 우회
    c.karmada_api_client = MagicMock()
    c.host_api_client = MagicMock()
    c.karmada_api_client.call_api.return_value = ({"ok": True}, 200, {})
    return c


MANIFEST = {"apiVersion": "apps/v1", "kind": "Deployment",
            "metadata": {"name": "x", "namespace": "sdi-demo"}, "spec": {"replicas": 1}}


def test_apply_serializes_body_for_apply_patch_yaml():
    """apply-patch+yaml 은 dict body 를 거부하므로 문자열(JSON)로 보내야 한다."""
    c = _client_with_mock()
    c.apply(MANIFEST)
    kwargs = c.karmada_api_client.call_api.call_args.kwargs
    assert isinstance(kwargs["body"], str)
    assert json.loads(kwargs["body"]) == MANIFEST
    assert kwargs["header_params"]["Content-Type"] == "application/apply-patch+yaml"


def test_apply_dry_run_sets_query_param():
    c = _client_with_mock()
    c.apply(MANIFEST, dry_run=True)
    kwargs = c.karmada_api_client.call_api.call_args.kwargs
    assert ("dryRun", "All") in kwargs["query_params"]
    assert ("fieldManager", "sdi-manifest-bridge") in kwargs["query_params"]


def test_apply_paths():
    c = _client_with_mock()
    c.apply(MANIFEST)
    path = c.karmada_api_client.call_api.call_args.args[0]
    assert path == "/apis/apps/v1/namespaces/sdi-demo/deployments/x"
    c.apply({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "cm", "namespace": "n"}})
    assert c.karmada_api_client.call_api.call_args.args[0] == "/api/v1/namespaces/n/configmaps/cm"
    c.apply({"apiVersion": "policy.karmada.io/v1alpha1", "kind": "PropagationPolicy",
             "metadata": {"name": "p", "namespace": "n"}})
    assert c.karmada_api_client.call_api.call_args.args[0].endswith("/propagationpolicies/p")


def test_apply_paths_cluster_scoped():
    """번들 안 Namespace 등 클러스터 범위 리소스는 namespaces/<ns> 없는 경로(예전에는 404)."""
    c = _client_with_mock()
    c.apply({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "sdi-etri-sim"}})
    assert c.karmada_api_client.call_api.call_args.args[0] == "/api/v1/namespaces/sdi-etri-sim"
    c.apply({"apiVersion": "rbac.authorization.k8s.io/v1", "kind": "ClusterRole", "metadata": {"name": "r"}})
    assert c.karmada_api_client.call_api.call_args.args[0] == "/apis/rbac.authorization.k8s.io/v1/clusterroles/r"
    c.apply({"apiVersion": "scheduling.k8s.io/v1", "kind": "PriorityClass", "metadata": {"name": "hc"}})
    assert c.karmada_api_client.call_api.call_args.args[0] == "/apis/scheduling.k8s.io/v1/priorityclasses/hc"
