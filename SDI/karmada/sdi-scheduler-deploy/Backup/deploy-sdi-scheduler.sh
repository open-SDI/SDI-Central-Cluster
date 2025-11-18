#!/bin/bash

set -e

echo "=== Deploying SDI Scheduler to sdi-system namespace ==="

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "Error: kubectl is not installed or not in PATH"
    exit 1
fi

# Step 1: Copy kubeconfig secret if needed
echo "Step 1: Checking kubeconfig secret..."
if ! kubectl get secret sdi-karmada-kubeconfig -n sdi-system >/dev/null 2>&1; then
    echo "Copying kubeconfig secret from karmada-system to sdi-system..."
    ./copy-kubeconfig-secret.sh
else
    echo "kubeconfig secret already exists in sdi-system namespace"
fi

# Step 2: Deploy SDI Scheduler
echo "Step 2: Deploying SDI Scheduler..."
kubectl apply -f sdi-cluster-scheduler-deploy.yaml

# Step 3: Wait for deployment to be ready
echo "Step 3: Waiting for deployment to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/sdi-cluster-scheduler -n sdi-system

echo "=== Deployment Status ==="
kubectl get pods -n sdi-system -l app=sdi-scheduler

echo "=== SDI Scheduler deployed successfully! ==="
echo ""
echo "To check logs:"
echo "  kubectl logs -n sdi-system -l app=sdi-scheduler -f"
echo ""
echo "To check services:"
echo "  kubectl get svc -n sdi-system"