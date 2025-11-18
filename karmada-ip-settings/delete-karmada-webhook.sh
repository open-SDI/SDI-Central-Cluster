#!/bin/bash

#0) 변수
NS=karmada-system

#1) Karmada 웹훅 끊기 (가장 중요)

웹훅이 살아있으면 삭제 API 호출이 전부 타임아웃 납니다.

kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations | grep -i karmada || true
# 위에서 나온 이름들 전부 삭제
for w in $(kubectl get validatingwebhookconfigurations -o name | grep -i karmada); do kubectl delete $w; done
for w in $(kubectl get mutatingwebhookconfigurations -o name | grep -i karmada); do kubectl delete $w; done

#2) 집계 APIService 끊기

karmada-aggregated-apiserver가 등록해둔 APIService가 남아 있으면 디스커버리 단계에서 막혀요.

for a in $(kubectl get apiservice -o name | grep -i karmada); do kubectl delete $a; done
