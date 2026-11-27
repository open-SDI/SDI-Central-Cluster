"""번들 일관성 검사 · 워크로드 분류 시험."""
import json

from sdi_manifest_bridge.core.bundle import IaCMaleBundle, convert_bundle
from sdi_manifest_bridge.core.consistency import (
    analyze_bundle, annotate_resources, bundle_warning_items, parse_catalog, parse_predictions, warning_strings,
    ANNO_CLASS, ANNO_FILLED, ANNO_WARNINGS,
)

CATALOG = parse_catalog("""
version: v0.1
workloads:
  - name: robot-control
    missionKind: drive
    c5: safety-function
    deadlineMs: 50
    kind: control
    byHwClass:
      HW-1: {expectedExecMs: 12, accel: none}
  - name: vision-detect
    missionKind: drive
    c5: mission-core
    deadlineMs: 100
    kind: inference
    placementHint: edge
    byHwClass:
      HW-2: {expectedExecMs: 40, accel: npu}
      HW-4: {expectedExecMs: 25, accel: gpu}
  - name: monitor-log
    missionKind: drive
    c5: aux
    deadlineMs: 1000
    kind: service
""")


def dep(name, image, cpu_limit=None, gpu=False, runtime=None, npu=False):
    res = {}
    if cpu_limit:
        res.setdefault('limits', {})['cpu'] = cpu_limit
    if gpu:
        res.setdefault('limits', {})['nvidia.com/gpu'] = 1
    if npu:
        res.setdefault('limits', {})['sdi.keti.dev/npu'] = 1
    spec = {'containers': [{'name': 'c', 'image': image, 'resources': res}]}
    if runtime:
        spec['runtimeClassName'] = runtime
    return {'id': name, 'manifest': {
        'apiVersion': 'apps/v1', 'kind': 'Deployment',
        'metadata': {'name': name, 'namespace': 'sdi-dev2'},
        'spec': {'selector': {'matchLabels': {'app': name}},
                 'template': {'metadata': {'labels': {'app': name}}, 'spec': spec}}}}


def binding(name, crit='B', period=None, wcet=None, deadline=None):
    mc = {'criticality': crit}
    if period: mc['rtPeriodMs'] = period
    if wcet: mc['rtWcetMs'] = wcet
    if deadline: mc['rtDeadlineMs'] = deadline
    return {'id': name, 'targetRef': {'manifestId': name, 'name': name},
            'importance': {'accuracy': 0.3, 'latency': 0.5, 'energy': 0.2}, 'mcSpec': mc}


def bundle(deps, binds):
    return IaCMaleBundle(bundleId='t', missionId='m', workloadManifests=deps, maleBindings=binds)


def codes(ws, who=None):
    return sorted(w['code'] for w in ws if who is None or w['binding'] == who)


def test_vision_cpu_only_warns_accel():
    b = bundle([dep('vision-detect', 'ultralytics/ultralytics:latest-cpu', '2')],
               [binding('vision-detect', 'C', deadline=100)])
    # 시험 카탈로그에는 CPU 실행시간(HW-1)이 없어 C7 이 기본값 → WARN_ACCEL_DEFAULT 도 함께
    assert codes(bundle_warning_items(b, CATALOG)) == ['ACCEL_NOT_REQUESTED', 'WARN_ACCEL_DEFAULT']
    # runtimeClass nvidia 로 GPU 를 쓰지만 자원 요청이 없음 → CPU 실행이 아니라 "GPU 를 셀 수 없음"
    b = bundle([dep('vision-detect', 'ultralytics/ultralytics:latest-cpu', '2', runtime='nvidia')],
               [binding('vision-detect', 'C', deadline=100)])
    assert codes(bundle_warning_items(b, CATALOG)) == ['GPU_NOT_ACCOUNTED', 'WARN_ACCEL_DEFAULT']


def test_gpu_without_runtimeclass():
    b = bundle([dep('vision-detect', 'ultralytics/ultralytics:latest', '2', gpu=True)],
               [binding('vision-detect', 'C', deadline=100)])
    assert codes(bundle_warning_items(b, CATALOG)) == ['GPU_NO_RUNTIMECLASS']
    b = bundle([dep('vision-detect', 'ultralytics/ultralytics:latest', '2', gpu=True, runtime='nvidia')],
               [binding('vision-detect', 'C', deadline=100)])
    assert bundle_warning_items(b, CATALOG) == []
    # NPU(sdi.keti.dev/npu)는 runtimeClass 없이 동작 → 경고 없음, 가속기 요청으로는 침
    b = bundle([dep('vision-detect', 'ultralytics/ultralytics:latest', '2', npu=True)],
               [binding('vision-detect', 'C', deadline=100)])
    assert bundle_warning_items(b, CATALOG) == []


def test_cpu_limit_and_wcet():
    b = bundle([dep('robot-control', 'ros:humble', '100m')],
               [binding('robot-control', 'C', period=50, wcet=60, deadline=40)])
    assert codes(bundle_warning_items(b, CATALOG)) == ['CPU_LIMIT_BELOW_UTIL', 'WARN_SAFETY_FROM_CATALOG', 'WCET_OVER_DEADLINE',
                                                  'WCET_OVER_PERIOD']
    b = bundle([dep('robot-control', 'ros:humble', '500m')],
               [binding('robot-control', 'C', period=50, wcet=12, deadline=50)])
    assert codes(bundle_warning_items(b, CATALOG)) == ['WARN_SAFETY_FROM_CATALOG']   # 번들에 safety 를 적으면 사라짐(아래 v2.0 시험)


def test_hc_no_deadline_and_role_unknown():
    b = bundle([dep('mystery', 'busybox')], [binding('mystery', 'C')])
    # 마감이 없고 주기 · 계기 · 라운드도 없으면 상시형(D = 1 s 기본) → HC_NO_DEADLINE 대신 C1 누락 경고
    assert codes(bundle_warning_items(b, CATALOG)) == ['MISSING_MISSION_KIND', 'ROLE_UNKNOWN']
    # 카탈로그가 마감을 주면 HC_NO_DEADLINE 없음
    b = bundle([dep('robot-control', 'ros:humble')], [binding('robot-control', 'C')])
    assert codes(bundle_warning_items(b, CATALOG)) == ['WARN_SAFETY_FROM_CATALOG']


def test_classification_sources():
    b = bundle([dep('robot-control', 'ros:humble'), dep('vision-detect', 'ultralytics/ultralytics', gpu=True, runtime='nvidia'),
                dep('mystery', 'my/yolo-app')],
               [binding('robot-control', 'C', deadline=30), binding('vision-detect'), binding('mystery')])
    a = analyze_bundle(b, CATALOG)
    rc = a['robot-control-workload']['classification']
    assert rc['C5'] == {'value': 'safety', 'source': 'catalog'}
    assert rc['D'] == {'value': 30, 'source': 'bundle'}          # 번들이 카탈로그보다 우선
    assert rc['C6'] == {'value': 'any', 'source': 'default'}     # v2.0 표 명시값 없으면 엣지 가능(까지 device-local)
    vd = a['vision-detect-workload']['classification']
    assert vd['C6'] == {'value': 'edge', 'source': 'catalog'} and vd['D']['source'] == 'catalog'
    my = a['mystery-workload']['classification']
    assert my['C2'] == {'value': 'inference', 'source': 'image'} and my['C5']['value'] is None
    assert my['C1'] == {'value': None, 'source': 'missing'}


def test_annotations_on_maleworkload():
    b = bundle([dep('vision-detect', 'ultralytics/ultralytics:latest-cpu')], [binding('vision-detect', 'C', deadline=100)])
    res = convert_bundle(b)
    ws = annotate_resources(b, res, CATALOG)
    mw = [r for r in res if r['kind'] == 'MaleWorkload'][0]
    ann = mw['metadata']['annotations']
    assert json.loads(ann[ANNO_CLASS])['C5']['value'] == 'core'
    assert json.loads(ann[ANNO_WARNINGS])[0]['code'] == 'ACCEL_NOT_REQUESTED' == ws[0]['code']
    # Deployment 등 다른 리소스는 건드리지 않음
    # (C 작업 PropagationPolicy 의 전달 보류 annotation 은 convert_bundle 이 붙인 것)
    assert all(set(((r.get('metadata') or {}).get('annotations') or {})) <= {'sdi.keti.dev/hold-dispatch'}
               for r in res if r['kind'] != 'MaleWorkload')


def test_no_catalog_still_works():
    b = bundle([dep('robot-control', 'ros:humble')], [binding('robot-control', 'B')])
    assert codes(bundle_warning_items(b, None)) == ['MISSING_MISSION_KIND', 'ROLE_UNKNOWN']


def test_warning_strings_format():
    ws = [{'binding': 'vision-detect', 'code': 'ACCEL_NOT_REQUESTED', 'message': 'x'}]
    assert warning_strings(ws) == ["maleBinding 'vision-detect': ACCEL_NOT_REQUESTED x"]


# 누락 보완: 카탈로그 → 예측표 → 기본값 순, 번들 값은 그대로
PREDS = parse_predictions("""
predictions:
  - {workload: navigation, hwClass: HW-4, cLoMs: 0.293, cHiMs: 4.473}
  - {workload: navigation, hwClass: HW-1, cLoMs: 20, cHiMs: 30}
  - {workload: vision-detect, hwClass: HW-4, cLoMs: 16, cHiMs: 32.4}
""")


def _mw(res, name):
    return [r for r in res if r['kind'] == 'MaleWorkload' and r['metadata']['name'] == name + '-workload'][0]


def test_fill_missing_order():
    b = bundle([dep('vision-detect', 'yolo'), dep('navigation', 'nav'), dep('robot-control', 'ros:humble'), dep('other', 'x')],
               [binding('vision-detect', 'B'), binding('navigation', 'B', period=100),
                binding('robot-control', 'C', wcet=9, deadline=40), binding('other', 'A')])
    res = convert_bundle(b)
    annotate_resources(b, res, CATALOG, PREDS)
    v = _mw(res, 'vision-detect')
    assert v['spec']['mcSpec']['rtDeadline'] == 100 and v['spec']['mcSpec']['rtWcet'] == 40  # 카탈로그(예측표보다 먼저)
    assert json.loads(v['metadata']['annotations'][ANNO_FILLED]) == {
        'rtDeadline': {'value': 100, 'source': 'catalog'}, 'rtWcet': {'value': 40, 'source': 'catalog'}}
    n = _mw(res, 'navigation')  # 카탈로그에 없음 → 예측표 cHi 최댓값 30, 마감은 주기
    assert json.loads(n['metadata']['annotations'][ANNO_FILLED]) == {
        'rtDeadline': {'value': 100, 'source': 'default-period'}, 'rtWcet': {'value': 30, 'source': 'predictions'}}
    r = _mw(res, 'robot-control')  # 번들 값 유지
    assert r['spec']['mcSpec']['rtWcet'] == 9 and r['spec']['mcSpec']['rtDeadline'] == 40
    assert ANNO_FILLED not in r['metadata']['annotations']
    o = _mw(res, 'other')  # 아무 데도 없으면 비워 둠
    assert 'rtWcet' not in o['spec']['mcSpec'] and ANNO_FILLED not in o['metadata']['annotations']


# --- 기술문서 v2.0 3장 분류 (표 예와 같은 결과) ---------------------------------

def _cls(dep_, bind_, catalog=CATALOG):
    b = bundle([dep_], [bind_])
    return analyze_bundle(b, catalog)[dep_['id'] + '-workload']['classification']


def test_v20_robot_control_like_w08():
    """W08 안전 회피(구동 · 제어 · 안전 기능 · Hard · CPU · 분할 불가 · 무상태). 주기가 있으면 주기형."""
    bd = binding('robot-control', 'C', period=50)
    bd['safety'] = True
    c = _cls(dep('robot-control', 'ros:humble'), bd)
    assert (c['C1']['value'], c['C2']['value'], c['C3']['value'], c['C4']['value'], c['C5']['value']) == \
        ('drive', 'control', 'periodic', 'hard', 'safety')
    assert c['C5']['source'] == 'bundle' and c['C4']['source'] == 'derived'
    assert (c['C7']['value'], c['C8']['value'], c['C9']['value']) == ('cpu', 'none', 'stateless')
    assert codes(bundle_warning_items(bundle([dep('robot-control', 'ros:humble', '500m')], [bd]), CATALOG)) == []


def test_v20_vision_npu_required_and_firm():
    """카탈로그: CPU(HW-1 없음) 시간이 없으면 NPU 선호 기본 + 경고, CPU 180 ms > 마감 100 이면 NPU 필수."""
    c = _cls(dep('vision-detect', 'ultralytics/ultralytics:cpu'), binding('vision-detect', 'B', period=100))
    assert c['C7'] == {'value': 'npuPreferred', 'source': 'default'}
    assert c['C4'] == {'value': 'firm', 'source': 'derived'}      # 미션 핵심 + 주기형
    cat = parse_catalog("""
workloads:
  - name: vision-detect
    missionKind: drive
    c5: mission-core
    kind: inference
    byHwClass:
      HW-1: {expectedExecMs: 180, accel: none}
      HW-2: {expectedExecMs: 40, accel: npu}
""")
    c = _cls(dep('vision-detect', 'ultralytics/ultralytics:cpu'), binding('vision-detect', 'B', deadline=100), cat)
    assert c['C7'] == {'value': 'npuRequired', 'source': 'catalog'}
    c = _cls(dep('vision-detect', 'ultralytics/ultralytics:cpu'), binding('vision-detect', 'B', deadline=300), cat)
    assert c['C7'] == {'value': 'npuPreferred', 'source': 'catalog'}


def test_v20_training_split_ckpt_like_w04():
    """W04 분할 학습 엣지 측(AI 분업 · 학습 · 배치형 · Soft · 미션 보조 · 엣지 · GPU 필요 · 분할 학습 · 체크포인트 가능)."""
    bd = binding('fl-edge', 'A', deadline=5000)
    bd.update(missionKind='ai-split', kind='training', rounds=10, placement='edge',
              splitConfigs=[{'cut': 'layer3'}], checkpoint={'supported': True})
    c = _cls(dep('fl-edge', 'pytorch/pytorch'), bd)
    assert [c[k]['value'] for k in ('C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9')] == \
        ['ai-split', 'training', 'batch', 'soft', 'assist', 'edge', 'gpu', 'splitTrain', 'ckpt']


def test_v20_service_continuous_default_deadline():
    """W11 모니터링처럼 주기 · 계기 · 라운드가 없으면 상시형, 마감 1 s 기본."""
    bd = binding('status-push', 'A')
    bd.update(missionKind='drive', kind='service')
    c = _cls(dep('status-push', 'busybox'), bd)
    assert c['C3'] == {'value': 'continuous', 'source': 'default'} and c['D'] == {'value': 1000, 'source': 'default'}
    assert c['C5'] == {'value': 'aux', 'source': 'derived'} and c['C4']['value'] == 'soft'


def test_v20_target_device_means_device_placement():
    bd = binding('pinned', 'A')
    bd['targetDevice'] = 'rpi5-npu-01'
    c = _cls(dep('pinned', 'busybox'), bd)
    assert c['C6'] == {'value': 'device', 'source': 'bundle-targetDevice'}


def test_bundle_safety_false_overrides_catalog_warns():
    # 번들 safety=false 가 카탈로그 안전 기능을 이기면 경고
    cat = {'robot-control': {'name': 'robot-control', 'c5': 'safety-function'}}
    b = bundle([dep('robot-control', 'ros:humble')], [binding('robot-control', 'C', deadline=50)])
    b.maleBindings[0].safety = False
    assert 'SAFETY_BUNDLE_OVERRIDES_CATALOG' in codes(bundle_warning_items(b, cat))
    b.maleBindings[0].safety = None
    assert 'SAFETY_BUNDLE_OVERRIDES_CATALOG' not in codes(bundle_warning_items(b, cat))


# 캐시가 만료돼도 요청은 옛 값을 바로 받고, 새로 읽기는 뒤 스레드 하나가 한다(요청이 다시 읽기를 기다리지 않음).
def test_cache_stale_served_while_refreshing_in_background():
    import threading
    import time
    from sdi_manifest_bridge.core import consistency as c
    gate, calls = threading.Event(), []

    def read():
        calls.append(1)
        gate.wait(2)
        return {'new': 1}

    cache = {'at': time.time() - 100, 'data': {'old': 1}}
    t0 = time.perf_counter()
    assert c._cached(cache, 30, read) == {'old': 1}
    assert c._cached(cache, 30, read) == {'old': 1}   # 읽는 중 → 스레드 더 안 띄움
    assert time.perf_counter() - t0 < 0.5
    gate.set()
    for _ in range(200):
        if not cache.get('busy'):
            break
        time.sleep(0.01)
    assert cache['data'] == {'new': 1} and len(calls) == 1
    assert c._cached(cache, 30, read) == {'new': 1}


def test_cache_first_load_in_request_and_keep_previous_on_failure():
    from sdi_manifest_bridge.core import consistency as c
    cache = {'at': 0.0, 'data': None}
    assert c._cached(cache, 30, lambda: {'v': 1}) == {'v': 1}

    def boom():
        raise RuntimeError('api down')

    c._refresh(cache, boom)
    assert cache['data'] == {'v': 1} and cache['busy'] is False


def test_yaml_c_loader_same_result():
    import yaml
    from sdi_manifest_bridge.core import consistency as c
    text = "workloads:\n  - {name: a, deadlineMs: 50, note: '한글', byHwClass: {HW-1: {expectedExecMs: 12.5, accel: null}}}\n"
    assert c._yaml(text) == yaml.safe_load(text)
    assert c._yaml('') is None


def test_fill_missing_measured_per_hw_class():
    """등급별로 실측이 카탈로그를 바꾸고, 실측 없는 등급은 카탈로그 그대로(최악 기준 최댓값)."""
    from sdi_manifest_bridge.core.consistency import fill_missing
    entry = {'byHwClass': {'HW-1': {'expectedExecMs': 12}, 'HW-2': {'expectedExecMs': 10}}}
    preds = {'robot-control': [
        {'workload': 'robot-control', 'hwClass': 'HW-1', 'cHiMs': 18.0, 'source': 'catalog'},
        {'workload': 'robot-control', 'hwClass': 'HW-2', 'cHiMs': 1.492, 'source': 'measured'}]}
    mc = {}
    assert fill_missing('robot-control', mc, entry, preds)['rtWcet'] == {'value': 12, 'source': 'catalog'}   # HW-1 미측정 → 12 그대로
    preds['robot-control'].append({'workload': 'robot-control', 'hwClass': 'HW-1', 'cHiMs': 3.2, 'source': 'measured'})
    mc = {}
    assert fill_missing('robot-control', mc, entry, preds)['rtWcet'] == {'value': 4, 'source': 'predictions-measured'}  # 둘 다 실측
    entry2 = {'byHwClass': {'HW-2': {'expectedExecMs': 10}}}
    mc = {}
    big = {'robot-control': [{'workload': 'robot-control', 'hwClass': 'HW-2', 'cHiMs': 14.0, 'source': 'measured'}]}
    assert fill_missing('robot-control', mc, entry2, big)['rtWcet'] == {'value': 14, 'source': 'predictions-measured'}  # 실측이 더 크면 실측
    mc = {'rtWcet': 7}
    assert 'rtWcet' not in fill_missing('robot-control', mc, entry, preds)   # 번들 값 유지
