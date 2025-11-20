package sdi

import (
	"context"
	"math"
	"strconv"

	clusterv1alpha1 "github.com/karmada-io/karmada/pkg/apis/cluster/v1alpha1"
	workv1alpha2 "github.com/karmada-io/karmada/pkg/apis/work/v1alpha2"
	"github.com/karmada-io/karmada/pkg/scheduler/framework"
)

type IntentDriven struct{}

func (i *IntentDriven) Name() string { return "IntentDriven" }

func (i *IntentDriven) Filter(_ context.Context,
	bs *workv1alpha2.ResourceBindingSpec,
	cl *clusterv1alpha1.Cluster,
	ale *ALE) framework.Code {

	if ale.Accuracy.ComputeIntensityTFLOPS >= 150 &&
		cl.Labels["accelerator"] != "gpu" {
		return framework.Unschedulable
	}
	return framework.Success
}

func (i *IntentDriven) Score(_ context.Context,
	_ *workv1alpha2.ResourceBindingSpec,
	cl *clusterv1alpha1.Cluster,
	ale *ALE) (int64, error) {

	budget := ale.Latency.Budget.P95
	if budget == 0 {
		return 500, nil
	}
	actual, _ := strconv.Atoi(cl.Labels["rtt-ms"])
	diff := float64(budget-actual) / float64(budget)
	if diff < 0 {
		diff = 0
	}
	return int64(math.Round(diff * 1000)), nil
}
