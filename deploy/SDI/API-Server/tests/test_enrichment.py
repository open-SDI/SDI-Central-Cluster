"""레거시 /v1/apply(/deploy) 경로: Ansible 입력 -> [Deployment, MaleWorkload, PropagationPolicy]."""
from sdi_manifest_bridge.core.enrichment import enrich_manifest


def test_enrich_manifest_basic():
    result = enrich_manifest({
        "mission": "mission-critical",
        "container_name": "data-processor",
        "image": "ubuntu:latest",
    })
    assert [r["kind"] for r in result] == ["Deployment", "MaleWorkload", "PropagationPolicy"]
    dep, mw, pp = result

    assert dep["metadata"]["name"] == "mission-critical-data-processor"
    assert dep["metadata"]["labels"]["mission"] == "mission-critical"
    container = dep["spec"]["template"]["spec"]["containers"][0]
    assert container["name"] == "data-processor"
    assert container["image"] == "ubuntu:latest"

    assert mw["spec"]["targetRef"] == {
        "apiVersion": "apps/v1", "kind": "Deployment", "name": "mission-critical-data-processor"}

    assert pp["spec"]["schedulerName"] == "sdi-scheduler"
    placement = pp["spec"]["placement"]
    assert "clusterAffinities" not in placement
    assert placement["spreadConstraints"] == [
        {"spreadByField": "cluster", "maxGroups": 1, "minGroups": 1}]


def test_enrich_manifest_with_all_options():
    result = enrich_manifest({
        "mission": "long-running-job",
        "container_name": "ml-worker",
        "image": "tensorflow/tensorflow:latest",
        "labels": {"team": "ml-team", "project": "project-x"},
        "annotations": {"monitoring.prometheus.io/scrape": "true"},
        "accuracy": 0.95,
        "latency": 0.5,
        "energy": 0.8,
        "criticality": "C",
    })
    dep, mw, _ = result

    assert dep["metadata"]["labels"]["mission"] == "long-running-job"
    assert dep["metadata"]["labels"]["team"] == "ml-team"
    assert dep["metadata"]["labels"]["project"] == "project-x"
    assert dep["metadata"]["annotations"]["monitoring.prometheus.io/scrape"] == "true"

    assert mw["spec"]["importance"] == {"accuracy": 0.95, "latency": 0.5, "energy": 0.8}
    assert mw["spec"]["mcSpec"]["criticality"] == "C"
