
import copy
import os
from typing import Dict, Any
from ruamel.yaml import YAML

# Initialize ruamel.yaml for round-trip loading and dumping
yaml = YAML()
yaml.indent(mapping=2, sequence=4, offset=2)

# ConfigMap에서 마운트될 템플릿 파일의 경로
POD_TEMPLATE_PATH = os.getenv("POD_TEMPLATE_PATH", "/etc/config/pod-template.yaml")

def load_template() -> Dict[str, Any]:
    """
    파일 시스템에서 기본 Pod 템플릿을 로드합니다.
    """
    try:
        with open(POD_TEMPLATE_PATH, 'r') as f:
            return yaml.load(f)
    except FileNotFoundError:
        # 테스트 또는 로컬 실행을 위한 폴백(fallback) 템플릿
        return {
            'apiVersion': 'v1',
            'kind': 'Pod',
            'metadata': {'labels': {}, 'annotations': {}},
            'spec': {
                'schedulerName': 'sdi-scheduler',
                'priorityClassName': 'real-time',
                'nodeSelector': {'role': 'edge'},
                'containers': [{'name': '', 'image': ''}]
            }
        }

# 애플리케이션 시작 시 템플릿을 한 번 로드
base_pod_template = load_template()

def enrich_manifest(user_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    사용자 입력을 기반으로 로드된 템플릿을 보강합니다.
    """
    # 원본 템플릿을 수정하지 않도록 깊은 복사 사용
    enriched_manifest = copy.deepcopy(base_pod_template)

    # --- 보강 규칙 적용 ---
    # 1. 메타데이터 생성 (이름)
    enriched_manifest['metadata']['name'] = f"{user_input.get('mission', 'default')}-{user_input.get('container_name', 'pod')}"
    enriched_manifest['metadata']['namespace'] = 'sdi-demo'

    # 2. 기본 필드 매핑
    enriched_manifest['spec']['containers'][0]['name'] = user_input.get('container_name')
    enriched_manifest['spec']['containers'][0]['image'] = user_input.get('image')

    # 3. 미션 레이블 및 어노테이션 처리
    if 'mission' in user_input:
        enriched_manifest['metadata']['labels']['mission'] = user_input['mission']
        enriched_manifest['metadata']['annotations']['male.sdi.dev/mission'] = user_input['mission']

    # 4. 사용자 정의 레이블 및 어노테이션 병합
    if user_input.get('labels'):
        enriched_manifest['metadata']['labels'].update(user_input['labels'])
    if user_input.get('annotations'):
        enriched_manifest['metadata']['annotations'].update(user_input['annotations'])

    # 5. MALE 어노테이션 추가
    for key in ['accuracy', 'latency', 'energy']:
        if user_input.get(key) is not None:
            enriched_manifest['metadata']['annotations'][f'male.sdi.dev/{key}'] = str(user_input[key])

    return enriched_manifest

def to_yaml_string(data: Dict[str, Any]) -> str:
    """
    딕셔너리를 YAML 문자열로 변환합니다.
    """
    from io import StringIO
    string_stream = StringIO()
    yaml.dump(data, string_stream)
    return string_stream.getvalue()

