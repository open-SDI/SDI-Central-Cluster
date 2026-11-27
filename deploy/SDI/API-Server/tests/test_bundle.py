"""IaCMaleBundle 검증/변환 테스트 (open-SDI/SDI-MALE-Interface Issue #1 합의 기준)."""
import pytest
from pydantic import ValidationError

import json

from sdi_manifest_bridge.core.bundle import (
    IaCMaleBundle, validate_bundle, convert_bundle, bundle_warnings, normalize_bundle,
)


def etri_example_bundle():
    """ETRI 예시 번들"""
    return {
        "apiVersion": "sdi.keti.dev/v1alpha1",
        "kind": "IaCMaleBundle",
        "bundleId": "etri-object-detection-001",
        "targetProfile": "kubernetes-karmada",
        "workloadManifests": [
            {
                "id": "deployment.object-detection",
                "manifest": {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": {"name": "object-detection", "namespace": "sdi-demo"},
                    "spec": {
                        "replicas": 1,
                        "selector": {"matchLabels": {"app": "object-detection"}},
                        "template": {
                            "metadata": {"labels": {"app": "object-detection"}},
                            "spec": {
                                "containers": [{
                                    "name": "detector",
                                    "image": "registry.example.com/sdi-detector:v0.1.0",
                                    "ports": [{"containerPort": 8080}],
                                    "resources": {
                                        "requests": {"cpu": "200m", "memory": "256Mi"},
                                        "limits": {"cpu": "500m", "memory": "512Mi"},
                                    },
                                }],
                            },
                        },
                    },
                },
            },
            {
                "id": "service.object-detection",
                "manifest": {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": "object-detection", "namespace": "sdi-demo"},
                    "spec": {
                        "selector": {"app": "object-detection"},
                        "ports": [{"protocol": "TCP", "port": 80, "targetPort": 8080}],
                        "type": "ClusterIP",
                    },
                },
            },
        ],
        "maleBindings": [
            {
                "id": "male.object-detection",
                "targetRef": {
                    "manifestId": "deployment.object-detection",
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "namespace": "sdi-demo",
                    "name": "object-detection",
                },
                "mission": "object-detection",
                "importance": {"accuracy": 0.3, "latency": 0.5, "energy": 0.2},
                "mcSpec": {
                    "criticality": "B",
                    "rtPeriodMs": 50,
                    "rtWcetMs": 20,
                    "rtDeadlineMs": 50,
                    "missionId": "object-detection",
                },
                "allowPolicyOverride": True,
            },
        ],
    }


def patrol_robot_bundle():
    """서브미션 2개(object-detection + slam)가 ConfigMap을 공유하는 다중 워크로드 번들."""

    def ros_deployment(name):
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": name, "namespace": "sdi-demo",
                         "labels": {"app": name, "mission": "patrol-robot"}},
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": {"app": name}},
                "template": {
                    "metadata": {"labels": {"app": name, "mission": "patrol-robot"}},
                    "spec": {
                        "hostNetwork": True,
                        "containers": [{
                            "name": name,
                            "image": f"registry.example.com/sdi-ros2-{name}:v0.1.0",
                            "env": [{"name": "CYCLONEDDS_URI",
                                     "value": "file:///config/cyclonedds.xml"}],
                            "volumeMounts": [{"name": "dds-config", "mountPath": "/config"}],
                        }],
                        "volumes": [{"name": "dds-config",
                                     "configMap": {"name": "cyclonedds-config"}}],
                    },
                },
            },
        }

    def binding(name, importance, rt):
        return {
            "id": f"male.{name}",
            "targetRef": {"manifestId": f"deployment.{name}", "apiVersion": "apps/v1",
                          "kind": "Deployment", "namespace": "sdi-demo", "name": name},
            "mission": name,
            "importance": importance,
            "mcSpec": {"criticality": "B", "rtPeriodMs": rt, "rtWcetMs": 20,
                       "rtDeadlineMs": rt, "missionId": "patrol-robot"},
            "allowPolicyOverride": True,
        }

    return {
        "apiVersion": "sdi.keti.dev/v1alpha1",
        "kind": "IaCMaleBundle",
        "bundleId": "etri-patrol-robot-001",
        "missionId": "patrol-robot",
        "workloadManifests": [
            {"id": "configmap.cyclonedds", "manifest": {
                "apiVersion": "v1", "kind": "ConfigMap",
                "metadata": {"name": "cyclonedds-config", "namespace": "sdi-demo"},
                "data": {"cyclonedds.xml": "<CycloneDDS/>"}}},
            {"id": "deployment.object-detection", "manifest": ros_deployment("object-detection")},
            {"id": "deployment.slam", "manifest": ros_deployment("slam")},
        ],
        "maleBindings": [
            binding("object-detection", {"accuracy": 0.6, "latency": 0.3, "energy": 0.1}, 50),
            binding("slam", {"accuracy": 0.1, "latency": 0.7, "energy": 0.2}, 100),
        ],
    }


# --- 검증 ------------------------------------------------------------------

def test_etri_example_passes_validation():
    bundle = IaCMaleBundle(**etri_example_bundle())
    assert validate_bundle(bundle) == []


def test_missing_manifest_id_rejected():
    data = etri_example_bundle()
    data["maleBindings"][0]["targetRef"]["manifestId"] = "deployment.typo"
    errors = validate_bundle(IaCMaleBundle(**data))
    assert len(errors) == 1
    assert "deployment.typo" in errors[0]
    assert "not found" in errors[0]


def test_target_mismatch_rejected():
    data = etri_example_bundle()
    data["maleBindings"][0]["targetRef"]["name"] = "wrong-name"
    errors = validate_bundle(IaCMaleBundle(**data))
    assert any("does not match" in e for e in errors)


def test_duplicate_manifest_id_rejected():
    data = etri_example_bundle()
    data["workloadManifests"].append(dict(data["workloadManifests"][0]))
    errors = validate_bundle(IaCMaleBundle(**data))
    assert any("duplicate workloadManifest id" in e for e in errors)


def test_invalid_criticality_rejected():
    data = etri_example_bundle()
    data["maleBindings"][0]["mcSpec"]["criticality"] = "Z"
    errors = validate_bundle(IaCMaleBundle(**data))
    assert any("criticality" in e for e in errors)


def test_importance_out_of_range_rejected_by_schema():
    data = etri_example_bundle()
    data["maleBindings"][0]["importance"]["accuracy"] = 1.5
    with pytest.raises(ValidationError):
        IaCMaleBundle(**data)


def test_empty_manifests_rejected_by_schema():
    data = etri_example_bundle()
    data["workloadManifests"] = []
    with pytest.raises(ValidationError):
        IaCMaleBundle(**data)


# --- 변환 ------------------------------------------------------------------

def by_kind(resources, kind):
    return [r for r in resources if r["kind"] == kind]


def test_etri_example_conversion():
    bundle = IaCMaleBundle(**etri_example_bundle())
    resources = convert_bundle(bundle)

    # 원본 manifest 2개 + MaleWorkload 1개 + PropagationPolicy 1개
    assert len(resources) == 4

    mw = by_kind(resources, "MaleWorkload")[0]
    # 합의: targetRef는 apiVersion/kind/name만, namespace는 metadata로
    assert mw["spec"]["targetRef"] == {
        "apiVersion": "apps/v1", "kind": "Deployment", "name": "object-detection"}
    assert mw["metadata"]["namespace"] == "sdi-demo"
    # 합의: 외부 API 단위 명시형 -> CRD 필드명 매핑
    assert mw["spec"]["mcSpec"]["rtPeriod"] == 50
    assert mw["spec"]["mcSpec"]["rtWcet"] == 20
    assert mw["spec"]["mcSpec"]["rtDeadline"] == 50
    assert "rtPeriodMs" not in mw["spec"]["mcSpec"]
    assert mw["spec"]["importance"] == {"accuracy": 0.3, "latency": 0.5, "energy": 0.2}

    # Service 는 Deployment 가 결정된 클러스터로 따라감: 정책에는 Deployment 만, propagateDeps + annotation
    pp = by_kind(resources, "PropagationPolicy")[0]
    selected = {(s["kind"], s["name"]) for s in pp["spec"]["resourceSelectors"]}
    assert selected == {("Deployment", "object-detection")}
    assert pp["spec"]["propagateDeps"] is True
    assert pp["spec"]["schedulerName"] == "sdi-scheduler"
    dep = by_kind(resources, "Deployment")[0]
    assert dep["metadata"]["annotations"]["sdi.keti.dev/dependent-services"] == "object-detection"


def test_support_in_selectors_when_follow_off(monkeypatch):
    """SDI_SUPPORT_FOLLOW_WORKLOAD=off 이면 예전처럼 Service 를 Deployment 정책의 resourceSelectors 에 넣는다."""
    monkeypatch.setenv("SDI_SUPPORT_FOLLOW_WORKLOAD", "off")
    resources = convert_bundle(IaCMaleBundle(**etri_example_bundle()))
    pp = by_kind(resources, "PropagationPolicy")[0]
    selected = {(s["kind"], s["name"]) for s in pp["spec"]["resourceSelectors"]}
    assert ("Service", "object-detection") in selected
    assert "propagateDeps" not in pp["spec"]
    dep = by_kind(resources, "Deployment")[0]
    assert "sdi.keti.dev/dependent-services" not in (dep["metadata"].get("annotations") or {})


def test_convert_does_not_change_input_bundle():
    """annotation 은 변환 결과 사본에만 붙고 입력 번들은 그대로."""
    bundle = IaCMaleBundle(**etri_example_bundle())
    convert_bundle(bundle)
    for wm in bundle.workloadManifests:
        assert "sdi.keti.dev/dependent-services" not in (wm.manifest.get("metadata", {}).get("annotations") or {})


def test_apply_order():
    bundle = IaCMaleBundle(**patrol_robot_bundle())
    kinds = [r["kind"] for r in convert_bundle(bundle)]
    # 합의된 순서: ConfigMap/Secret -> 워크로드 -> MaleWorkload -> PropagationPolicy
    assert kinds.index("ConfigMap") < kinds.index("Deployment")
    assert max(i for i, k in enumerate(kinds) if k == "Deployment") \
        < min(i for i, k in enumerate(kinds) if k == "MaleWorkload")
    assert max(i for i, k in enumerate(kinds) if k == "MaleWorkload") \
        < min(i for i, k in enumerate(kinds) if k == "PropagationPolicy")


def test_apply_order_policy_first(monkeypatch):
    """SDI_APPLY_POLICY_FIRST=on 이면 MaleWorkload · PP 가 워크로드보다 먼저(Deployment 가 들어오자마자 RB)."""
    monkeypatch.setenv("SDI_APPLY_POLICY_FIRST", "on")
    bundle = IaCMaleBundle(**patrol_robot_bundle())
    kinds = [r["kind"] for r in convert_bundle(bundle)]
    first_deploy = min(i for i, k in enumerate(kinds) if k == "Deployment")
    assert kinds.index("ConfigMap") < first_deploy
    assert max(i for i, k in enumerate(kinds) if k in ("MaleWorkload", "PropagationPolicy")) < first_deploy


def test_patrol_robot_mission_grouping():
    bundle = IaCMaleBundle(**patrol_robot_bundle())
    resources = convert_bundle(bundle)

    workloads = by_kind(resources, "MaleWorkload")
    assert len(workloads) == 2
    # 서브미션 규약: mission = 서브미션 이름, mcSpec.missionId = 상위 미션
    for mw in workloads:
        assert mw["spec"]["mcSpec"]["missionId"] == "patrol-robot"
    assert {mw["spec"]["mission"] for mw in workloads} == {"object-detection", "slam"}

    # 정책은 Deployment 마다 하나, 공유 ConfigMap 은 propagateDeps 로 각 Deployment 를 따라감
    policies = by_kind(resources, "PropagationPolicy")
    assert len(policies) == 2
    assert all(p["spec"]["propagateDeps"] is True for p in policies)
    assert not any(s["kind"] == "ConfigMap" for p in policies for s in p["spec"]["resourceSelectors"])


def test_patrol_robot_shared_configmap_follow_off(monkeypatch):
    """예전 방식: 공유 ConfigMap 은 첫 번째 Deployment 의 정책에만 포함(중복 selector 방지)."""
    monkeypatch.setenv("SDI_SUPPORT_FOLLOW_WORKLOAD", "off")
    policies = by_kind(convert_bundle(IaCMaleBundle(**patrol_robot_bundle())), "PropagationPolicy")
    cm_owners = [p for p in policies
                 if any(s["kind"] == "ConfigMap" for s in p["spec"]["resourceSelectors"])]
    assert len(cm_owners) == 1


def test_bundle_mission_id_fallback():
    """binding의 mcSpec.missionId가 없으면 번들 최상위 missionId를 사용한다."""
    data = patrol_robot_bundle()
    for b in data["maleBindings"]:
        del b["mcSpec"]["missionId"]
    resources = convert_bundle(IaCMaleBundle(**data))
    for mw in by_kind(resources, "MaleWorkload"):
        assert mw["spec"]["mcSpec"]["missionId"] == "patrol-robot"


# --- 정정 규칙 -------------------------------------------------------

from sdi_manifest_bridge.core.bundle import bundle_warnings


def test_target_ref_manifest_id_only_passes():
    """targetRef는 manifestId만 있어도 되고, 나머지는 매니페스트에서 유도한다."""
    data = etri_example_bundle()
    data["maleBindings"][0]["targetRef"] = {"manifestId": "deployment.object-detection"}
    bundle = IaCMaleBundle(**data)
    assert validate_bundle(bundle) == []
    mw = by_kind(convert_bundle(bundle), "MaleWorkload")[0]
    assert mw["spec"]["targetRef"] == {
        "apiVersion": "apps/v1", "kind": "Deployment", "name": "object-detection"}
    assert mw["metadata"]["namespace"] == "sdi-demo"


def test_importance_sum_must_be_one():
    data = etri_example_bundle()
    data["maleBindings"][0]["importance"] = {"accuracy": 0.5, "latency": 0.5, "energy": 0.5}
    errors = validate_bundle(IaCMaleBundle(**data))
    assert any("importance" in e and "sum" in e for e in errors)


def test_importance_sum_tolerance():
    data = etri_example_bundle()
    data["maleBindings"][0]["importance"] = {"accuracy": 0.333, "latency": 0.333, "energy": 0.333}
    assert validate_bundle(IaCMaleBundle(**data)) == []


def test_mission_id_mismatch_rejected():
    data = patrol_robot_bundle()
    data["maleBindings"][0]["mcSpec"]["missionId"] = "other-mission"
    errors = validate_bundle(IaCMaleBundle(**data))
    assert any("missionId" in e and "other-mission" in e for e in errors)


def test_rt_zero_rejected():
    data = etri_example_bundle()
    data["maleBindings"][0]["mcSpec"]["rtPeriodMs"] = 0
    errors = validate_bundle(IaCMaleBundle(**data))
    assert any("rtPeriodMs" in e and "positive" in e for e in errors)


def test_wcet_over_deadline_rejected():
    data = etri_example_bundle()
    data["maleBindings"][0]["mcSpec"]["rtWcetMs"] = 80
    data["maleBindings"][0]["mcSpec"]["rtDeadlineMs"] = 50
    errors = validate_bundle(IaCMaleBundle(**data))
    assert any("rtWcetMs" in e and "rtDeadlineMs" in e for e in errors)


def test_constrained_deadline_accepted():
    """deadline <= period 는 정상(constrained deadline). 거부하지 않는다."""
    data = etri_example_bundle()
    data["maleBindings"][0]["mcSpec"]["rtDeadlineMs"] = 30
    data["maleBindings"][0]["mcSpec"]["rtPeriodMs"] = 50
    bundle = IaCMaleBundle(**data)
    assert validate_bundle(bundle) == []
    assert bundle_warnings(bundle) == []


def test_arbitrary_deadline_warns_not_rejects():
    """deadline > period 는 경고 후 수용(arbitrary deadline)."""
    data = etri_example_bundle()
    data["maleBindings"][0]["mcSpec"]["rtDeadlineMs"] = 300
    data["maleBindings"][0]["mcSpec"]["rtPeriodMs"] = 66
    bundle = IaCMaleBundle(**data)
    assert validate_bundle(bundle) == []
    warnings = bundle_warnings(bundle)
    assert len(warnings) == 1 and "arbitrary" in warnings[0]


def test_criticality_only_binding_is_valid():
    """RT 값 없이 등급만 있는 최소 케이스."""
    data = etri_example_bundle()
    data["maleBindings"][0]["mcSpec"] = {"criticality": "A"}
    bundle = IaCMaleBundle(**data)
    assert validate_bundle(bundle) == []
    mw = by_kind(convert_bundle(bundle), "MaleWorkload")[0]
    assert mw["spec"]["mcSpec"] == {"criticality": "A"}


def test_missing_criticality_defaults_to_lowest():
    """협의 규격: criticality 는 선택. 없으면 A(바닥값 없음) + 경고 + filled 기록(예전: 거부)."""
    for drop in ("mcSpec", "criticality"):
        data = etri_example_bundle()
        if drop == "mcSpec":
            del data["maleBindings"][0]["mcSpec"]
        else:
            del data["maleBindings"][0]["mcSpec"]["criticality"]
        b = IaCMaleBundle(**data)
        assert validate_bundle(b) == []
        assert any("criticality not given" in w for w in bundle_warnings(b))
        mw = next(r for r in convert_bundle(b) if r["kind"] == "MaleWorkload")
        assert mw["spec"]["mcSpec"]["criticality"] == "A"
        assert json.loads(mw["metadata"]["annotations"]["sdi.keti.dev/filled"])["criticality"]["source"] == "default-lowest"


# --- PropagationPolicy placement (contracts.md 5절) ------------------------------

def test_propagation_policy_single_cluster_no_algorithm_hardcode():
    """알고리즘은 스케줄러가 고른다: affinityName 하드코딩 없이 클러스터 1곳만 선택."""
    resources = convert_bundle(IaCMaleBundle(**etri_example_bundle()))
    for pp in by_kind(resources, "PropagationPolicy"):
        placement = pp["spec"]["placement"]
        assert "clusterAffinities" not in placement
        assert placement["spreadConstraints"] == [
            {"spreadByField": "cluster", "maxGroups": 1, "minGroups": 1}]
        assert placement["clusterTolerations"] == []
        assert pp["spec"]["schedulerName"] == "sdi-scheduler"


# --- IaC 알고리즘 지정 -------------------------------------------------

def test_scheduling_algorithm_annotation():
    data = etri_example_bundle()
    data["schedulingAlgorithm"] = "swarm"
    mw = by_kind(convert_bundle(IaCMaleBundle(**data)), "MaleWorkload")[0]
    assert mw["metadata"]["annotations"]["sdi.keti.dev/scheduler-algorithm"] == "collaborative-swarm"
    data["maleBindings"][0]["schedulingAlgorithm"] = "Predictive_Context"  # 바인딩 값이 우선
    mw = by_kind(convert_bundle(IaCMaleBundle(**data)), "MaleWorkload")[0]
    assert mw["metadata"]["annotations"]["sdi.keti.dev/scheduler-algorithm"] == "predictive-context"


def test_scheduling_algorithm_absent_and_invalid():
    mw = by_kind(convert_bundle(IaCMaleBundle(**etri_example_bundle())), "MaleWorkload")[0]
    assert "annotations" not in mw["metadata"]
    data = etri_example_bundle()
    data["maleBindings"][0]["schedulingAlgorithm"] = "fastest"
    errors = validate_bundle(IaCMaleBundle(**data))
    assert len(errors) == 1 and "schedulingAlgorithm 'fastest'" in errors[0]


# --- MissionWorkload 명세 항목 -------------------------------------------

def test_mission_workload_spec_annotation():
    import json
    data = etri_example_bundle()
    b = data["maleBindings"][0]
    b["mcSpec"].pop("rtDeadlineMs", None)
    b["maleTargets"] = {"targetAccuracy": 0.9, "latencyBudgetMs": 80, "powerBudgetW": 15}
    b["model"] = {"type": "yolov5s", "sizeMB": 14.1, "gflops": 16.5}
    mw = by_kind(convert_bundle(IaCMaleBundle(**data)), "MaleWorkload")[0]
    spec = json.loads(mw["metadata"]["annotations"]["sdi.keti.dev/mission-workload"])
    assert spec["maleTargets"] == {"targetAccuracy": 0.9, "latencyBudgetMs": 80, "powerBudgetW": 15}
    assert spec["model"] == {"type": "yolov5s", "sizeMB": 14.1, "gflops": 16.5}
    assert "resources" in spec
    # 마감이 없으면 latencyBudget 을 마감으로
    assert mw["spec"]["mcSpec"]["rtDeadline"] == 80
    assert json.loads(mw["metadata"]["annotations"]["sdi.keti.dev/filled"])["rtDeadline"]["source"] == "bundle-latencyBudget"


def test_battery_intent_reaches_annotation():
    """maleTargets.minBatteryPct · missionDurationS 가 mission-workload 어노테이션으로 (스케줄러 battery-intent 입력)."""
    import json
    data = etri_example_bundle()
    data["maleBindings"][0]["maleTargets"] = {"minBatteryPct": 40, "missionDurationS": 600}
    mw = by_kind(convert_bundle(IaCMaleBundle(**data)), "MaleWorkload")[0]
    spec = json.loads(mw["metadata"]["annotations"]["sdi.keti.dev/mission-workload"])
    assert spec["maleTargets"] == {"minBatteryPct": 40, "missionDurationS": 600}
    for bad in ({"minBatteryPct": 120}, {"missionDurationS": 0}):
        data["maleBindings"][0]["maleTargets"] = bad
        with pytest.raises(ValidationError):
            IaCMaleBundle(**data)


def test_mission_workload_spec_validation():
    data = etri_example_bundle()
    data["maleBindings"][0]["maleTargets"] = {"targetAccuracy": 1.5}
    with pytest.raises(ValidationError):
        IaCMaleBundle(**data)


# --- HC 후보 전달 보류 (Operator 노드 고정 전 비실시간 노드 배치 방지) ----------

def test_hc_candidate_policy_holds_dispatch(monkeypatch):
    monkeypatch.delenv("SDI_HOLD_HC_DISPATCH", raising=False)
    data = etri_example_bundle()
    data["maleBindings"][0]["mcSpec"]["criticality"] = "C"
    pp = by_kind(convert_bundle(IaCMaleBundle(**data)), "PropagationPolicy")[0]
    assert pp["spec"]["suspension"] == {"dispatching": True}
    assert pp["metadata"]["annotations"]["sdi.keti.dev/hold-dispatch"] == "until-device-tier"


def test_non_hc_policy_dispatches_and_env_off(monkeypatch):
    data = etri_example_bundle()
    data["maleBindings"][0]["mcSpec"]["criticality"] = "B"
    pp = by_kind(convert_bundle(IaCMaleBundle(**data)), "PropagationPolicy")[0]
    assert "suspension" not in pp["spec"] and "annotations" not in pp["metadata"]
    monkeypatch.setenv("SDI_HOLD_HC_DISPATCH", "off")   # 끄면 C 도 보류하지 않음
    data["maleBindings"][0]["mcSpec"]["criticality"] = "C"
    pp = by_kind(convert_bundle(IaCMaleBundle(**data)), "PropagationPolicy")[0]
    assert "suspension" not in pp["spec"]


# --- 기체 지정 ---------------------------------------------------------

def test_target_device_annotation():
    data = etri_example_bundle()
    data["maleBindings"][0]["targetDevice"] = " rpi5-npu-01 "
    mw = by_kind(convert_bundle(IaCMaleBundle(**data)), "MaleWorkload")[0]
    assert mw["metadata"]["annotations"]["sdi.keti.dev/target-device"] == "rpi5-npu-01"
    mw = by_kind(convert_bundle(IaCMaleBundle(**etri_example_bundle())), "MaleWorkload")[0]
    assert "sdi.keti.dev/target-device" not in (mw["metadata"].get("annotations") or {})


def test_target_device_policy_holds_dispatch(monkeypatch):
    # 기체 지정 작업은 등급이 C 가 아니어도 고정 전 전달 보류
    monkeypatch.delenv("SDI_HOLD_HC_DISPATCH", raising=False)
    data = etri_example_bundle()
    data["maleBindings"][0]["mcSpec"]["criticality"] = "A"
    data["maleBindings"][0]["targetDevice"] = "rpi5-npu-01"
    pp = by_kind(convert_bundle(IaCMaleBundle(**data)), "PropagationPolicy")[0]
    assert pp["spec"]["suspension"] == {"dispatching": True}
    data["maleBindings"][0]["targetDevice"] = "  "   # 빈 값이면 보류 안 함
    pp = by_kind(convert_bundle(IaCMaleBundle(**data)), "PropagationPolicy")[0]
    assert "suspension" not in pp["spec"]


def test_prepin_target_skips_hold(monkeypatch):
    # SDI_PREPIN_TARGET=on 이면 "클러스터/노드" 기체 지정 HC 는 보류하지 않음(Operator 가 결정 전에 고정)
    monkeypatch.delenv("SDI_HOLD_HC_DISPATCH", raising=False)
    monkeypatch.setenv("SDI_PREPIN_TARGET", "on")
    data = etri_example_bundle()
    data["maleBindings"][0]["mcSpec"]["criticality"] = "C"
    data["maleBindings"][0]["targetDevice"] = "edge-cluster-239/turtlebot-edge-01"
    pp = by_kind(convert_bundle(IaCMaleBundle(**data)), "PropagationPolicy")[0]
    assert "suspension" not in pp["spec"]
    data["maleBindings"][0]["targetDevice"] = "turtlebot-edge-01"   # 클러스터를 모르면 고정 못 하니 보류 유지
    pp = by_kind(convert_bundle(IaCMaleBundle(**data)), "PropagationPolicy")[0]
    assert pp["spec"]["suspension"] == {"dispatching": True}
    monkeypatch.delenv("SDI_PREPIN_TARGET")
    data["maleBindings"][0]["targetDevice"] = "edge-cluster-239/turtlebot-edge-01"
    pp = by_kind(convert_bundle(IaCMaleBundle(**data)), "PropagationPolicy")[0]
    assert pp["spec"]["suspension"] == {"dispatching": True}


def test_hold_prepinned_nonhc(monkeypatch):
    # SDI_HOLD_PREPINNED_NONHC=on 이면 기체 지정(사전 고정) MC/LC 는 보류, HC 는 그대로 보류 안 함. 끄면 예전과 같음
    monkeypatch.delenv("SDI_HOLD_HC_DISPATCH", raising=False)
    monkeypatch.setenv("SDI_PREPIN_TARGET", "on")
    data = etri_example_bundle()
    data["maleBindings"][0]["targetDevice"] = "edge-cluster-239/turtlebot-burger-2"
    pin = lambda crit: (data["maleBindings"][0]["mcSpec"].__setitem__("criticality", crit),
                        by_kind(convert_bundle(IaCMaleBundle(**data)), "PropagationPolicy")[0]["spec"])[1]
    assert "suspension" not in pin("A")          # 끔(기본): 예전처럼 보류 안 함
    monkeypatch.setenv("SDI_HOLD_PREPINNED_NONHC", "on")
    assert pin("A")["suspension"] == {"dispatching": True}
    assert pin("B")["suspension"] == {"dispatching": True}
    assert "suspension" not in pin("C")          # HC 는 배치 지연 때문에 계속 보류 안 함


# --- 번들 등급 입력 → Operator annotation (grade.male.keti.dev/*) ---------------

def grade_ann(data):
    mw = by_kind(convert_bundle(IaCMaleBundle(**data)), "MaleWorkload")[0]
    return {k[len("grade.male.keti.dev/"):]: v for k, v in (mw["metadata"].get("annotations") or {}).items()
            if k.startswith("grade.male.keti.dev/")}


def test_grade_annotations_from_bundle():
    # 번들에 아무것도 없으면 붙이지 않음 → Operator 가 카탈로그를 씀(예전과 같음)
    assert grade_ann(etri_example_bundle()) == {}
    data = etri_example_bundle()
    b = data["maleBindings"][0]
    b.update(safety=True, role="support", strictness="HARD", placement="device", kind="training", splitConfigs=[{"cut": 3}])
    assert grade_ann(data) == {"safety": "true", "role": "assist", "strictness": "hard",
                               "path": "device-local", "workload-class": "split-training"}
    # usage driving-perception 도 안전 기능, 기체 지정이면 경로 device-local, safety=false 는 그대로 전달
    data = etri_example_bundle()
    data["maleBindings"][0].update(usage="driving-perception", targetDevice="rpi5-npu-01", kind="deploy")
    assert grade_ann(data) == {"safety": "true", "path": "device-local", "workload-class": "model-deploy"}
    data = etri_example_bundle()
    data["maleBindings"][0].update(safety=False, placement="edge", role="unknown-role", kind="inference")
    assert grade_ann(data) == {"safety": "false", "path": "edge"}
    # placement any 는 경로를 정하지 않음(Operator 카탈로그 · 기본값)
    data = etri_example_bundle()
    data["maleBindings"][0].update(placement="any")
    assert grade_ann(data) == {}


# --- ETRI 협의 규격(이슈 "IaCMaleBundle 입력 규격 확정 및 연동 방식") ----------------

def agreed_spec_bundle():
    """이슈 3절 예시와 같은 형태: 새 칸만 쓰고 mcSpec · importance(motor-control) 는 생략."""
    data = etri_example_bundle()
    dep = data["workloadManifests"][0]
    motor = json.loads(json.dumps(dep))
    motor["id"] = "deployment.motor-control"
    motor["manifest"]["metadata"]["name"] = "motor-control"
    data["workloadManifests"].append(motor)
    data["missionId"] = "patrol-robot"
    data["missionType"] = "realtime-robotics"
    data["missionAtomicity"] = "criticalOnly"
    data["maleBindings"] = [
        {"id": "male.motor-control", "targetRef": {"manifestId": "deployment.motor-control"},
         "mission": "motor-control", "criticality": "C", "placement": "deviceLocked",
         "targetDevice": "turtlebot-01", "rtSpec": {"periodMs": 20, "deadlineMs": 20},
         "missionRequirements": {"minBatteryPct": 30, "missionDurationS": 600}},
        {"id": "male.object-detection", "targetRef": {"manifestId": "deployment.object-detection"},
         "mission": "object-detection", "criticality": "B", "placement": "flexible",
         "importance": {"accuracy": 0.5, "latency": 0.4, "energy": 0.1},
         "rtSpec": {"periodMs": 100, "deadlineMs": 100}, "missionRequirements": {"targetAccuracy": 0.8}},
    ]
    return data


def _mw(resources, name):
    return next(r for r in resources if r["kind"] == "MaleWorkload" and r["metadata"]["name"] == f"{name}-workload")


def test_agreed_spec_valid_and_converted():
    b = IaCMaleBundle(**agreed_spec_bundle())
    assert validate_bundle(b) == []
    res = convert_bundle(b)
    motor, det = _mw(res, "motor-control"), _mw(res, "object-detection")
    # criticality · rtSpec → mcSpec
    assert motor["spec"]["mcSpec"] == {"criticality": "C", "rtPeriod": 20, "rtDeadline": 20, "missionId": "patrol-robot"}
    assert det["spec"]["mcSpec"]["criticality"] == "B" and det["spec"]["mcSpec"]["rtDeadline"] == 100
    # importance 생략 → missionType 기본값, 준 값은 그대로
    assert motor["spec"]["importance"] == {"accuracy": 0.1, "latency": 0.7, "energy": 0.2}
    assert det["spec"]["importance"] == {"accuracy": 0.5, "latency": 0.4, "energy": 0.1}
    a = motor["metadata"]["annotations"]
    assert json.loads(a["sdi.keti.dev/filled"])["importance"]["source"] == "missionType:realtime-robotics"
    assert a["sdi.keti.dev/mission-type"] == "realtime-robotics" and a["sdi.keti.dev/mission-atomicity"] == "criticalOnly"
    # placement deviceLocked → 등급 경로 device-local, 기체 지정, missionRequirements → mission-workload maleTargets
    assert a["grade.male.keti.dev/path"] == "device-local"
    assert a["sdi.keti.dev/target-device"] == "turtlebot-01"
    assert json.loads(a["sdi.keti.dev/mission-workload"])["maleTargets"] == {"minBatteryPct": 30.0, "missionDurationS": 600.0}
    assert "grade.male.keti.dev/path" not in det["metadata"]["annotations"]   # flexible = 위치 제약 없음
    # HC(C) 는 전달 보류 PP
    pp = next(r for r in res if r["kind"] == "PropagationPolicy" and r["metadata"]["name"] == "motor-control-policy")
    assert pp["spec"]["suspension"] == {"dispatching": True}


def test_agreed_spec_minimal():
    """가장 단순한 입력: missionId · missionType + targetRef · mission 만."""
    data = agreed_spec_bundle()
    data.pop("missionAtomicity")
    data["maleBindings"] = [{"targetRef": {"manifestId": "deployment.object-detection"}, "mission": "object-detection"}]
    b = IaCMaleBundle(**data)
    assert validate_bundle(b) == []
    mw = _mw(convert_bundle(b), "object-detection")
    assert mw["spec"]["mcSpec"]["criticality"] == "A"
    assert mw["spec"]["importance"] == {"accuracy": 0.1, "latency": 0.7, "energy": 0.2}


def test_agreed_spec_rejections():
    cases = [
        (lambda d: d.update(missionAtomicity="all"), "missionAtomicity"),
        (lambda d: d["maleBindings"][0].update(criticality="D"), "criticality must be one of A/B/C"),
        (lambda d: d["maleBindings"][0].update(placement="onboard"), "placement"),
        (lambda d: d["maleBindings"][0].update(mcSpec={"criticality": "B"}), "conflicts with mcSpec.criticality"),
        (lambda d: d["maleBindings"][0].update(mcSpec={"criticality": "C", "rtPeriodMs": 50}), "rtSpec.periodMs"),
        (lambda d: d["maleBindings"][1].pop("criticality"), "criticalOnly needs criticality"),
    ]
    for mutate, msg in cases:
        data = agreed_spec_bundle(); mutate(data)
        errors = validate_bundle(IaCMaleBundle(**data))
        assert any(msg in e for e in errors), (msg, errors)


def test_unknown_mission_type_accepted_with_warning():
    """모르는 missionType 은 거부하지 않고 경고, importance 없는 바인딩은 같은 비중."""
    data = agreed_spec_bundle()
    data["missionType"] = "llm-training"
    for b in data["maleBindings"]:
        b.pop("importance", None)
    b = IaCMaleBundle(**data)
    assert validate_bundle(b) == []
    w = bundle_warnings(b)
    assert any("missionType 'llm-training'" in x for x in w)
    assert any("equal weights" in x for x in w)
    assert _mw(convert_bundle(b), "motor-control")["spec"]["importance"] == {"accuracy": 0.34, "latency": 0.33, "energy": 0.33}


def test_c_without_device_locked_warns():
    """C 이면서 deviceLocked 가 아니면 B 로 대우된다는 경고."""
    data = agreed_spec_bundle()
    data["maleBindings"][0]["placement"] = "flexible"
    w = bundle_warnings(IaCMaleBundle(**data))
    assert any("treated as B" in x for x in w)
    ok = bundle_warnings(IaCMaleBundle(**agreed_spec_bundle()))
    assert not any("treated as B" in x for x in ok)


def test_agreed_spec_rtspec_must_be_positive():
    data = agreed_spec_bundle()
    data["maleBindings"][0]["rtSpec"] = {"periodMs": 0}
    with pytest.raises(ValidationError):
        IaCMaleBundle(**data)


def test_normalize_is_idempotent_and_keeps_input():
    b = IaCMaleBundle(**agreed_spec_bundle())
    n1, e1, _ = normalize_bundle(b)
    n2, e2, w2 = normalize_bundle(n1)
    assert e1 == e2 == [] and w2 == []
    assert n1.model_dump() == n2.model_dump()
    assert b.maleBindings[0].mcSpec is None   # 원본 입력은 바꾸지 않음


def test_equal_weights_when_no_importance_nor_mission_type():
    data = agreed_spec_bundle()
    data.pop("missionType")
    b = IaCMaleBundle(**data)
    assert validate_bundle(b) == []
    assert any("equal weights" in w for w in bundle_warnings(b))
    assert _mw(convert_bundle(b), "motor-control")["spec"]["importance"] == {"accuracy": 0.34, "latency": 0.33, "energy": 0.33}


def test_hold_all_dispatch_env(monkeypatch):
    """SDI_HOLD_ALL_DISPATCH=on 이면 MC/LC(B · A)도 전달 보류, 기본은 HC 만."""
    data = agreed_spec_bundle()
    pp = lambda res, n: next(r for r in res if r["kind"] == "PropagationPolicy" and r["metadata"]["name"] == f"{n}-policy")
    res = convert_bundle(IaCMaleBundle(**data))
    assert "suspension" not in pp(res, "object-detection")["spec"]
    monkeypatch.setenv("SDI_HOLD_ALL_DISPATCH", "on")
    res = convert_bundle(IaCMaleBundle(**data))
    assert pp(res, "object-detection")["spec"]["suspension"] == {"dispatching": True}
    assert pp(res, "motor-control")["spec"]["suspension"] == {"dispatching": True}


def test_hold_skip_edge_path(monkeypatch):
    """SDI_HOLD_SKIP_EDGE_PATH=on 이면 placement edge 인 비 HC 는 HOLD_ALL 이어도 보류 안 함. HC · 지정 없음은 그대로 보류."""
    data = agreed_spec_bundle()
    pp = lambda res, n: next(r for r in res if r["kind"] == "PropagationPolicy" and r["metadata"]["name"] == f"{n}-policy")
    for mb in data["maleBindings"]:
        if mb["targetRef"]["manifestId"].endswith("object-detection") or "object-detection" in str(mb.get("id", "")):
            mb["placement"] = "edge"
    monkeypatch.setenv("SDI_HOLD_ALL_DISPATCH", "on")
    res = convert_bundle(IaCMaleBundle(**data))
    assert pp(res, "object-detection")["spec"]["suspension"] == {"dispatching": True}   # 스위치 꺼짐: 예전과 같음
    monkeypatch.setenv("SDI_HOLD_SKIP_EDGE_PATH", "on")
    res = convert_bundle(IaCMaleBundle(**data))
    assert "suspension" not in pp(res, "object-detection")["spec"]
    assert pp(res, "motor-control")["spec"]["suspension"] == {"dispatching": True}      # 경로 지정 없음 · HC 는 그대로 보류


def test_unknown_mission_type_no_warning_when_all_importance_given():
    """모든 바인딩이 importance 를 주면 기본 가중치 경고를 내지 않음."""
    data = agreed_spec_bundle()
    data["missionType"] = "warehouse-inspection"
    for b in data["maleBindings"]:
        b["importance"] = {"accuracy": 0.5, "latency": 0.3, "energy": 0.2}
    w = bundle_warnings(IaCMaleBundle(**data))
    assert not any("has no default importance" in x for x in w)


def test_unknown_target_device_warns_only_on_render(monkeypatch):
    """없는 장치 이름(cart-17)은 render(check_devices=True) 에서만 경고, 있는 이름 · cluster/node 는 통과."""
    import sdi_manifest_bridge.core.validate as B   # bundle_warnings 가 known_nodes 를 찾는 모듈
    monkeypatch.setattr(B, "known_nodes", lambda ttl=30.0: {"turtlebot-waffle-1": "edge-cluster-42"})
    data = agreed_spec_bundle()
    data["maleBindings"][0]["targetDevice"] = "cart-17"
    b = IaCMaleBundle(**data)
    assert any("UNKNOWN_TARGET_DEVICE" in x for x in bundle_warnings(b, check_devices=True))
    assert not any("UNKNOWN_TARGET_DEVICE" in x for x in bundle_warnings(b))
    for ok in ("turtlebot-waffle-1", "edge-cluster-42/turtlebot-waffle-1"):
        data["maleBindings"][0]["targetDevice"] = ok
        assert not any("UNKNOWN_TARGET_DEVICE" in x for x in bundle_warnings(IaCMaleBundle(**data), check_devices=True))
    data["maleBindings"][0]["targetDevice"] = "edge-cluster-43/turtlebot-waffle-1"
    assert any("UNKNOWN_TARGET_DEVICE" in x for x in bundle_warnings(IaCMaleBundle(**data), check_devices=True))
    monkeypatch.setattr(B, "known_nodes", lambda ttl=30.0: None)   # 히트맵 못 읽으면 경고 안 함
    data["maleBindings"][0]["targetDevice"] = "cart-17"
    assert not any("UNKNOWN_TARGET_DEVICE" in x for x in bundle_warnings(IaCMaleBundle(**data), check_devices=True))
