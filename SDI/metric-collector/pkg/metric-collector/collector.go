package metriccollector

import (
	"context"
	"fmt"
	"time"

	v1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/metrics/pkg/client/clientset/versioned"
)

type NodeMetric struct {
	Name            string
	CPUUsage        *resource.Quantity
	MemoryUsage     *resource.Quantity
	CPUCapacity     *resource.Quantity
	MemoryCapacity  *resource.Quantity
	CPUAllocatable  *resource.Quantity
	MemoryAllocatable *resource.Quantity
	Timestamp       time.Time
}

type Collector struct {
	clientset    kubernetes.Interface
	metricsClient versioned.Interface
}

func NewCollector(clientset kubernetes.Interface, metricsClient versioned.Interface) *Collector {
	return &Collector{
		clientset:    clientset,
		metricsClient: metricsClient,
	}
}

func (c *Collector) Collect(ctx context.Context) ([]NodeMetric, error) {
	nodeMetricsList, err := c.metricsClient.MetricsV1beta1().NodeMetricses().List(ctx, metav1.ListOptions{})
	if err != nil {
		return nil, fmt.Errorf("failed to get node metrics: %w", err)
	}

	nodes, err := c.clientset.CoreV1().Nodes().List(ctx, metav1.ListOptions{})
	if err != nil {
		return nil, fmt.Errorf("failed to list nodes: %w", err)
	}

	var collectedMetrics []NodeMetric

	nodeInfoMap := make(map[string]v1.Node)
	for _, node := range nodes.Items {
		nodeInfoMap[node.Name] = node
	}

	for _, nm := range nodeMetricsList.Items {
		node, ok := nodeInfoMap[nm.Name]
		if !ok {
			continue
		}

		metric := NodeMetric{
			Name:            nm.Name,
			CPUUsage:        nm.Usage.Cpu(),
			MemoryUsage:     nm.Usage.Memory(),
			CPUCapacity:     node.Status.Capacity.Cpu(),
			MemoryCapacity:  node.Status.Capacity.Memory(),
			CPUAllocatable:  node.Status.Allocatable.Cpu(),
			MemoryAllocatable: node.Status.Allocatable.Memory(),
			Timestamp:       nm.Timestamp.Time,
		}
		collectedMetrics = append(collectedMetrics, metric)
	}

	return collectedMetrics, nil
}
