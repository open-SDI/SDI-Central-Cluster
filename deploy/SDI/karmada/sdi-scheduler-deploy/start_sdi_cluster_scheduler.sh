#!/bin/bash

#실행방법인데 이거 보고 직접해야함
kubectl apply -f sdi-cluster-scheduler-deploy.yaml
kubectl delete secret sdi-karmada-kubeconfig -n sdi-system --ignore-not-found=true
sudo cat /etc/karmada/karmada-apiserver.config > clean-kubeconfig.yaml
kubectl create secret generic sdi-karmada-kubeconfig -n sdi-system --from-file=kubeconfig=./clean-kubeconfig.yaml
kubectl rollout restart deployment sdi-cluster-scheduler -n sdi-system
rm -rf clean-kubeconfig.yaml
