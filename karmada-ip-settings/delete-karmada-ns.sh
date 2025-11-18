#!/bin/bash

NS=karmada-system

# 상태 확인 (deletionTimestamp / finalizers)
kubectl get ns $NS -o jsonpath='{.metadata.deletionTimestamp}{" / "}{.spec.finalizers}{"\n"}'

# 강제 finalize (네임스페이스 파이널라이저 비우기)
kubectl get ns $NS -o json > /tmp/ns.json
jq '.spec.finalizers=[]' /tmp/ns.json > /tmp/ns-finalize.json
kubectl replace --raw "/api/v1/namespaces/$NS/finalize" -f /tmp/ns-finalize.json

# 없어졌는지 확인
kubectl get ns $NS || echo "namespace removed"
