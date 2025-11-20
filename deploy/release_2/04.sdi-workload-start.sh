#!/bin/bash

echo "=========================================="
echo "🚀 SDI Workload Scheduling System Starting..."
echo "=========================================="
echo "📡 Connecting to Turtlebot Edge Cluster..."
echo "🎯 Target Pod: sdi-workload-3"
echo "⚙️  Scheduler: sdi-scheduler"
echo ""

echo "📋 Deploying workload to Turtlebot..."
kubectl apply -f SDI-Orchestration/SDI-Scheduler/test-SDI-Scheduler.yaml

echo ""
echo "⏳ Monitoring pod status for 10 seconds..."
timeout 10s kubectl get pods -w --field-selector=metadata.name=sdi-workload-3 || true

echo ""
echo "📊 Final pod status:"
kubectl get pods --field-selector=metadata.name=sdi-workload-3

echo ""
echo "✅ SDI Workload deployment completed!"
echo "🤖 Turtlebot is now processing the workload..."
echo "=========================================="
