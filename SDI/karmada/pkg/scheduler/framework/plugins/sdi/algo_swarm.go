package sdi

import (
	"context"
	"math"

	corev1 "k8s.io/api/core/v1"

	clusterv1alpha1 "github.com/karmada-io/karmada/pkg/apis/cluster/v1alpha1"
	workv1alpha2 "github.com/karmada-io/karmada/pkg/apis/work/v1alpha2"
	"github.com/karmada-io/karmada/pkg/scheduler/framework"
)

type CollaborativeSwarm struct{}

func (c *CollaborativeSwarm) Name() string { return "CollaborativeSwarm" }

func (c *CollaborativeSwarm) Filter(_ context.Context,
	_ *workv1alpha2.ResourceBindingSpec,
	_ *clusterv1alpha1.Cluster,
	_ *ALE) framework.Code {
	return framework.Success
}

func (c *CollaborativeSwarm) Score(_ context.Context,
	bs *workv1alpha2.ResourceBindingSpec,
	cl *clusterv1alpha1.Cluster,
	ale *ALE) (int64, error) {

	_ = bs 
	score := int64(0)

	if ale.Latency.Region != "" &&
		cl.Labels["topology.kubernetes.io/region"] == ale.Latency.Region {
		score += 400
	}

	if ale.Energy.EnergyClass == "Low" && cl.Labels["energy"] == "low" {
		score += 300
	}

	rs := cl.Status.ResourceSummary
	if rs.Allocatable != nil && rs.Allocated != nil {
		qCPUAlloc := rs.Allocatable[corev1.ResourceCPU]
		qCPUUsed := rs.Allocated[corev1.ResourceCPU]
		tcpu := qCPUAlloc.MilliValue()
		ucpu := qCPUUsed.MilliValue()

		qMemAlloc := rs.Allocatable[corev1.ResourceMemory]
		qMemUsed := rs.Allocated[corev1.ResourceMemory]
		tmem := qMemAlloc.Value()
		umem := qMemUsed.Value()

		if tcpu > 0 && tmem > 0 {
			freeCPU := float64(tcpu-ucpu) / float64(tcpu)
			freeMem := float64(tmem-umem) / float64(tmem)
			if freeCPU < 0 { freeCPU = 0 }
			if freeMem  < 0 { freeMem  = 0 }
			score += int64(math.Round((freeCPU + freeMem) * 150))
		}
	}

	if score > 1000 { score = 1000 }
	return score, nil
}
