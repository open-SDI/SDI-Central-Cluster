
import logging
import json
from fastapi import FastAPI, Body, Query, HTTPException, Response
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from kubernetes.client.exceptions import ApiException

from .core.enrichment import enrich_manifest, to_yaml_string
from .k8s.client import k8s_client

# --- 로깅 설정 ---
# 구조화된 로깅을 위해 JSON 포맷으로 로그를 남깁니다.
logging.basicConfig(level=logging.INFO, format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}')


# --- Pydantic 모델 정의 ---
class SdiManifestInput(BaseModel):
    """
    Represents the simplified input from Ansible.
    """
    mission: str = Field(..., description="The mission identifier for the pod.")
    container_name: str = Field(..., description="Name of the container.")
    image: str = Field(..., description="The container image to use.")
    
    annotations: Optional[Dict[str, str]] = Field(default=None)
    labels: Optional[Dict[str, str]] = Field(default=None)
    accuracy: Optional[float] = Field(default=None, ge=0, le=1)
    latency: Optional[float] = Field(default=None, ge=0, le=1)
    energy: Optional[float] = Field(default=None, ge=0, le=1)

    class Config:
        extra = '''allow'''

# --- FastAPI 앱 초기화 ---
app = FastAPI(
    title="SDI Manifest Bridge",
    description="Receives simplified manifests, enriches them, and applies them to Kubernetes.",
    version="0.2.0", # 버전 업데이트
)


# --- API 엔드포인트 ---
@app.get("/healthz", tags=["Monitoring"])
def health_check():
    return {"status": "ok"}

@app.post("/v1/render", tags=["Manifests"], response_class=Response)
async def render_manifest(manifest_input: SdiManifestInput = Body(...)):
    user_input_dict = manifest_input.model_dump(exclude_unset=True)
    enriched_dict = enrich_manifest(user_input_dict)
    
    # 생성된 YAML을 로그로 기록
    log_payload = {
        "event": "ManifestRendered",
        "request": user_input_dict,
        "generated_manifest": enriched_dict
    }
    logging.info(json.dumps(log_payload))

    yaml_output = to_yaml_string(enriched_dict)
    return Response(content=yaml_output, media_type="application/x-yaml")

@app.post("/v1/apply", tags=["Manifests"])
async def apply_manifest(
    dry_run: bool = Query(True, description="If true, performs a server-side dry run. If false, applies the resource."),
    manifest_input: SdiManifestInput = Body(...)
):
    user_input_dict = manifest_input.model_dump(exclude_unset=True)
    enriched_manifest = enrich_manifest(user_input_dict)

    # 적용할 YAML을 로그로 기록
    log_payload = {
        "event": "ManifestApplyAttempt",
        "dry_run": dry_run,
        "request": user_input_dict,
        "final_manifest": enriched_manifest
    }
    logging.info(json.dumps(log_payload))

    try:
        result = k8s_client.apply(manifest=enriched_manifest, dry_run=dry_run)
        
        response_data = {
            "status": "Success",
            "dry_run": dry_run,
            "resource": {
                "kind": result.get("kind"),
                "name": result.get("metadata", {}).get("name"),
                "namespace": result.get("metadata", {}).get("namespace"),
            },
        }
        if not dry_run:
            response_data["resource"]["uid"] = result.get("metadata", {}).get("uid")
            response_data["resource"]["resource_version"] = result.get("metadata", {}).get("resourceVersion")

        logging.info(json.dumps({"event": "ManifestApplySuccess", "result": response_data}))
        return response_data

    except ApiException as e:
        logging.error(json.dumps({"event": "ManifestApplyFailed", "error": {"status": e.status, "reason": e.reason, "body": e.body}}))
        raise HTTPException(status_code=e.status, detail=e.body)
    except Exception as e:
        logging.error(json.dumps({"event": "ManifestApplyFailed", "error": str(e)}))
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

