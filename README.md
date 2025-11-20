# KETI SDI Central Cluster

Multi-cluster based scheduling and orchestration platform for Kubernetes workloads with focus on edge computing and machine learning acceleration.

## Overview

This repository contains the complete implementation of a multi-cluster orchestration system designed for managing distributed workloads across central and edge clusters. The platform provides intelligent scheduling, policy-based workload management, and real-time metric collection for optimal resource utilization.

## Key Features

- **Custom Kubernetes Scheduler**: SDI-Scheduler with TurtleBot battery and location-aware scheduling
- **Policy-Based Workload Management**: MALE Controller for ML workload optimization
- **Multi-Cluster Orchestration**: Karmada integration for cross-cluster workload deployment
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
| **Karmada Integration** | Multi-cluster orchestration | Karmada, Kubernetes |

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
│   └── SDI/                          # Core SDI platform modules
├── infrastructure/
│   └── networking/tunnel/            # Networking and tunneling utilities
├── scripts/
│   ├── cluster/                      # Operational scripts (e.g., IP auto patch)
│   └── etri-setup/                   # Provisioning helpers (kept intact)
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

### 7. Karmada Integration

Multi-cluster orchestration configuration.

**Location**: `deploy/SDI/karmada/`, `deploy/SDI/male-controller/karmada-integration/`

### 8. Network Auto-Patch Script

Automated Kubernetes IP management script.

**Location**: `scripts/cluster/sdi_platform_network_auto_patch.sh`

## Prerequisites

- Kubernetes 1.20+
- k3s v1.32.5+
- kubectl v1.11.3+
- Go v1.24.0+
- Python 3.12+
- InfluxDB v2.x

## Quick Start

### 1. Install k3s

```bash
curl -sfL https://get.k3s.io | sh -
```

### 2. Deploy Components

```bash
# Metric Collector
cd release_2/SDI-Orchestration/Metric-Collector
kubectl apply -f Metric-Collector-deploy.yaml

# SDI-Scheduler
cd ../SDI-Scheduler
kubectl apply -f SDI-Scheduler-deploy.yaml

# MALE Components
cd ../MALE-Advisor
kubectl apply -f MALE-Advisor-deploy.yaml

cd ../MALE-Profiler
kubectl apply -f MALE-Profiler-deploy.yaml
```

## Documentation

- **SDI-Orchestration Guide**: `deploy/release_2/SDI-Orchestration/README.md`
- **MALE Controller**: `deploy/SDI/male-controller/README.md`

## License

Copyright 2025. Licensed under the Apache License, Version 2.0.
