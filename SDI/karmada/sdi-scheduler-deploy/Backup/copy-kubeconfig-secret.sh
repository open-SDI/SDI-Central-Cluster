#!/bin/bash

# Copy kubeconfig secret from karmada-system to sdi-system namespace
echo "Copying kubeconfig secret from karmada-system to sdi-system..."

# Check if karmada-kubeconfig secret exists in karmada-system
if ! kubectl get secret karmada-kubeconfig -n karmada-system >/dev/null 2>&1; then
    echo "Error: karmada-kubeconfig secret not found in karmada-system namespace"
    exit 1
fi

# Check if sdi-system namespace exists
if ! kubectl get namespace sdi-system >/dev/null 2>&1; then
    echo "Creating sdi-system namespace..."
    kubectl create namespace sdi-system
fi

# Copy and rename the secret
kubectl get secret karmada-kubeconfig -n karmada-system -o yaml | \
  sed 's/namespace: karmada-system/namespace: sdi-system/' | \
  sed 's/name: karmada-kubeconfig/name: sdi-karmada-kubeconfig/' | \
  kubectl apply -f -

if [ $? -eq 0 ]; then
    echo "Successfully copied kubeconfig secret to sdi-system namespace"
else
    echo "Failed to copy kubeconfig secret"
    exit 1
fi