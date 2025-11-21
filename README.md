# KETI SDI Central Cluster

Multi-cluster based scheduling and orchestration platform for Kubernetes workloads with focus on edge computing and machine learning acceleration.

## Overview

This repository contains the complete implementation of a multi-cluster orchestration system designed for managing distributed workloads across central and edge clusters. The platform provides intelligent scheduling, policy-based workload management, and real-time metric collection for optimal resource utilization.

## Key Features

- **Custom Kubernetes Scheduler**: SDI-Scheduler with TurtleBot battery and location-aware scheduling
- **Policy-Based Workload Management**: MALE Controller for ML workload optimization
- **Multi-Cluster Orchestration**: Karmada integration for cross-cluster workload deployment
- **Airgap-Ready Installation**: Complete offline installation support with automated detection
- **Real-time Metrics**: InfluxDB-based metric collection and analysis
- **Network Auto-Patching**: Automated Kubernetes IP management
- **ROS2 Support**: Distributed ROS2 node orchestration

## Architecture

### Core Components

| Component | Description | Technology |
|-----------|-------------|------------|
| **SDI-Scheduler** | Custom Kubernetes scheduler for mixed-criticality workloads | Go, Kubernetes Scheduler Framework |
| **MALE Controller** | Kubernetes Operator for ML workload policy management | Go, Kubebuilder, CRD |
| **MALE-Advisor** | Policy decision engine based on A-L-E Score | Python, gRPC |
| **MALE-Profiler** | Workload profiling and analysis module | Python |
| **Analysis Engine** | Metric analysis and device management | Python, InfluxDB |
| **Metric-Collector** | System and device metric collection | Python, InfluxDB |
| **Karmada** | Multi-cluster orchestration and workload distribution | Karmada v1.15.2 |

## Project Structure

```
KETI_SDI_Central_Cluster/
├── backups/
│   └── pki/                          # PKI material backups
├── configs/
│   ├── central-cluster/              # ETRI server configuration
│   ├── karmada/                      # Karmada configs and IP policies
│   └── kubernetes/                   # Cluster-scoped manifests (k3s, CoreDNS, etc.)
├── deploy/
│   ├── release_2/                    # Release-grade orchestration bundle
│   │   └── SDI-Orchestration/        # SDI-Scheduler, MALE-Advisor, MALE-Profiler, Metric-Collector
│   └── SDI/                          # Core SDI platform modules
│       ├── male-controller/          # MALE Controller with Karmada integration
│       ├── analysis-engine/          # Analysis Engine
│       └── karmada/                  # Karmada deployment configs
├── infrastructure/
│   └── networking/tunnel/            # Networking and tunneling utilities
├── scripts/
│   ├── cluster/                      # Operational scripts (e.g., IP auto patch)
│   └── etri-setup/                   # Provisioning and setup helpers
│       ├── karmada/                  # Karmada installation and management scripts
│       └── network/                  # Network control scripts
└── src/                              # Standalone services and libraries
```

## Components

### 1. SDI-Scheduler

Custom Kubernetes scheduler that performs workload scheduling based on:
- TurtleBot battery status
- Device location information
- Mixed-criticality scheduling algorithm
- InfluxDB metric integration

**Location**: `deploy/release_2/SDI-Orchestration/SDI-Scheduler/`

### 2. MALE Controller

Kubernetes Operator built with Kubebuilder that manages MALEPolicy CRD for ML workload optimization.

**Features**:
- A-L-E Score based policy management (Accuracy, Latency, Energy)
- Workload targeting via labels, namespaces, or direct specification
- Real-time policy application through annotations and environment variables
- Karmada multi-cluster integration

**Location**: `deploy/SDI/male-controller/`

### 3. MALE-Advisor (Policy Engine)

Policy decision engine that determines optimal MALE policies based on A-L-E Score.

**Location**: `deploy/release_2/SDI-Orchestration/MALE-Advisor/`

### 4. MALE-Profiler (Analysis Engine)

Workload profiling module that analyzes collected metrics and generates performance characteristics.

**Location**: `deploy/release_2/SDI-Orchestration/MALE-Profiler/`

### 5. Analysis Engine

Python-based analysis engine for processing metrics and managing SDI devices.

**Location**: `deploy/SDI/analysis-engine/`

### 6. Metric-Collector

Metric collection stack including InfluxDB time-series database.

**Location**: `deploy/release_2/SDI-Orchestration/Metric-Collector/` and `deploy/SDI/cluster-metric-collector/`

### 7. Karmada Multi-Cluster Orchestration

Complete Karmada v1.15.2 installation and management system with airgap support.

**Features**:
- Automated airgap/online mode detection
- Universal cluster join supporting k3s and k8s
- SSH-based remote cluster management
- Complete offline installation toolkit
- Multi-cluster deployment testing

**Location**: `scripts/etri-setup/karmada/`

**Quick Start**:
```bash
cd scripts/etri-setup/karmada

# Install Karmada (auto-detects airgap mode)
./install-karmada.sh

# Join clusters
./join-cluster.sh edge-cluster /etc/rancher/k3s/k3s.yaml root@10.0.0.39 ketilinux

# Check status
./check-status.sh

# Test deployment
./test-deployment.sh
```

**Documentation**:
- Complete Guide: `scripts/etri-setup/karmada/README.md`
- Quick Start: `scripts/etri-setup/karmada/QUICKSTART.md`
- Testing Guide: `scripts/etri-setup/karmada/TEST-GUIDE.md`

### 8. Network Auto-Patch Script

Automated Kubernetes IP management script for handling IP changes without external network access.

**Features**:
- Automatic IP detection and replacement
- Kubernetes configuration backup
- API server certificate regeneration
- Component restart automation

**Location**: `scripts/cluster/sdi_platform_network_auto_patch.sh`

## Prerequisites

- **Kubernetes**: 1.20+ (or k3s v1.32+)
- **Container Runtime**: containerd 1.7+ or Docker
- **kubectl**: v1.11.3+
- **Go**: v1.24.0+ (for building)
- **Python**: 3.12+ (for MALE components)
- **InfluxDB**: v2.x
- **Karmada**: v1.15.2 (automated installation available)

## Quick Start

### 1. Install Kubernetes Cluster

**Option A: k3s (Recommended for Edge)**
```bash
curl -sfL https://get.k3s.io | sh -
```

**Option B: kubeadm (Full Kubernetes)**
```bash
# See Kubernetes documentation
kubeadm init --pod-network-cidr=10.244.0.0/16
```

### 2. Install Karmada (Multi-Cluster Orchestration)

```bash
cd scripts/etri-setup/karmada

# Download required files (internet-connected environment)
cd download-scripts
./download-karmadactl.sh
./download-karmada-images.sh
./download-karmada-crds.sh
cd ..

# Install Karmada (works in airgap mode)
./install-karmada.sh

# Join member clusters
./join-cluster.sh edge-cluster /etc/rancher/k3s/k3s.yaml root@10.0.0.39 ketilinux

# Verify installation
./check-status.sh
```

### 3. Deploy SDI Components

```bash
# Metric Collector
cd deploy/release_2/SDI-Orchestration/Metric-Collector
kubectl apply -f Metric-Collector-deploy.yaml

# SDI-Scheduler
cd ../SDI-Scheduler
kubectl apply -f SDI-Scheduler-deploy.yaml

# MALE Components
cd ../MALE-Advisor
kubectl apply -f MALE-Advisor-deploy.yaml

cd ../MALE-Profiler
kubectl apply -f MALE-Profiler-deploy.yaml

# MALE Controller
cd ../../../../deploy/SDI/male-controller
kubectl apply -f male-controller.yaml
```

### 4. Test Multi-Cluster Deployment

```bash
cd scripts/etri-setup/karmada
./test-deployment.sh
```

## Configuration

### Network Management

**Block external network** (for airgap testing):
```bash
cd scripts/etri-setup/network
./01.block_network_option.sh
```

**Restore network**:
```bash
./04.restore_network_option.sh
```

### IP Change Management

When cluster IP changes:
```bash
cd scripts/cluster
./sdi_platform_network_auto_patch.sh
```

## Documentation

### Core Platform
- **SDI-Orchestration Guide**: `deploy/release_2/SDI-Orchestration/README.md`
- **MALE Controller**: `deploy/SDI/male-controller/README.md`

### Karmada Multi-Cluster
- **Complete Guide**: `scripts/etri-setup/karmada/README.md`
- **Quick Start**: `scripts/etri-setup/karmada/QUICKSTART.md`
- **Testing Guide**: `scripts/etri-setup/karmada/TEST-GUIDE.md`
- **Download Scripts**: `scripts/etri-setup/karmada/download-scripts/README.md`

## Testing

### Multi-Cluster Deployment Test

```bash
cd scripts/etri-setup/karmada

# Run automated test
./test-deployment.sh

# Monitor deployment
./verify-deployment.sh

# Cleanup
./cleanup-test.sh
```

### Verify Karmada Status

```bash
# Check Karmada pods
kubectl get pods -n karmada-system

# Check member clusters
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config get clusters

# Check test deployments
kubectl --kubeconfig=/etc/karmada/karmada-apiserver.config get deployment -n karmada-test
```

## System Requirements

### Central Cluster (Control Plane)
- **OS**: Ubuntu 22.04 LTS
- **CPU**: 4+ cores
- **Memory**: 8GB+ RAM
- **Storage**: 50GB+
- **Network**: Internal network access to edge clusters

### Edge Clusters
- **OS**: Ubuntu 22.04 LTS or compatible
- **CPU**: 2+ cores
- **Memory**: 4GB+ RAM
- **Storage**: 20GB+
- **Network**: Connectivity to central cluster

## Airgap Installation

For completely offline environments:

1. **Prepare files** (internet-connected machine):
   ```bash
   cd scripts/etri-setup/karmada/download-scripts
   ./download-karmadactl.sh
   ./download-karmada-images.sh
   ./download-karmada-crds.sh
   ```

2. **Transfer to airgap environment**:
   ```bash
   scp -r karmada/ user@airgap-server:/path/
   ```

3. **Install in airgap** (auto-detects offline mode):
   ```bash
   cd karmada
   ./install-karmada.sh
   ./join-cluster.sh edge-cluster /etc/rancher/k3s/k3s.yaml root@10.0.0.39 ketilinux
   ```

## Troubleshooting

### Karmada Installation Issues

See detailed troubleshooting in `scripts/etri-setup/karmada/README.md`

Common issues:
- **KUBECONFIG error**: `unset KUBECONFIG` or `export KUBECONFIG=/root/.kube/config`
- **Missing images**: Run download scripts in internet-connected environment
- **Pod pending**: Check node taints with `kubectl describe node`

### Network Issues

If Kubernetes API server IP changes:
```bash
cd scripts/cluster
./sdi_platform_network_auto_patch.sh
```

## Contributing

This is a research project by KETI (Korea Electronics Technology Institute).

## License

Copyright 2025 KETI. Licensed under the Apache License, Version 2.0.

## Contact

For questions or issues, please contact the KETI SDI team.

---

**Version**: 1.0.0  
**Last Updated**: 2025-11-21  
**Karmada Version**: v1.15.2  
**Kubernetes Version**: v1.34.2 (central), k3s v1.33.4 (edge)
