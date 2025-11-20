#!/bin/bash

echo "=== Checking Karmada Connection ==="

# Check if we can access Karmada CRDs
echo "1. Checking Karmada CRDs..."
kubectl api-resources | grep karmada || echo "No Karmada CRDs found"

echo ""
echo "2. Checking for Karmada API groups..."
kubectl api-versions | grep karmada || echo "No Karmada API groups found"

echo ""
echo "3. Current kubeconfig context:"
kubectl config current-context

echo ""
echo "4. Current server URL:"
kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}'

echo ""
echo ""
echo "=== If Karmada CRDs are not found ==="
echo "The scheduler needs to connect to the Karmada control plane, not a regular Kubernetes cluster."
echo ""
echo "You need to:"
echo "1. Make sure you're using the correct kubeconfig that points to Karmada control plane"
echo "2. The kubeconfig should have access to:"
echo "   - clusters.cluster.karmada.io"
echo "   - resourcebindings.work.karmada.io" 
echo "   - clusterresourcebindings.work.karmada.io"
echo ""
echo "3. Update the secret with the correct kubeconfig:"
echo "   kubectl create secret generic sdi-karmada-kubeconfig \\"
echo "     --from-file=kubeconfig=/path/to/karmada-kubeconfig \\"
echo "     -n sdi-system --dry-run=client -o yaml | kubectl apply -f -"