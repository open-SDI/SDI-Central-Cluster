package metriccollector

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
)

type RabbitPublisher struct {
	conn      *amqp.Connection
	channel   *amqp.Channel
	queueName string
}

func NewRabbitPublisher() (*RabbitPublisher, error) {
	host := getenv("RABBITMQ_HOST", "rabbitmq")
	user := getenv("RABBITMQ_USER", "rabbit")
	pass := getenv("RABBITMQ_PASS", "rabbit")
	q    := getenv("RABBITMQ_QUEUE", "node.metrics")

	url := fmt.Sprintf("amqp://%s:%s@%s/", user, pass, host)
	conn, err := amqp.Dial(url)
	if err != nil {
		return nil, fmt.Errorf("dial rabbitmq: %w", err)
	}

	ch, err := conn.Channel()
	if err != nil {
		conn.Close()
		return nil, fmt.Errorf("open channel: %w", err)
	}

	if _, err := ch.QueueDeclare(q, true, false, false, false, nil); err != nil {
		conn.Close()
		return nil, fmt.Errorf("declare queue: %w", err)
	}

	return &RabbitPublisher{conn, ch, q}, nil
}

func (p *RabbitPublisher) Close() {
	if p.channel != nil {
		_ = p.channel.Close()
	}
	if p.conn != nil {
		_ = p.conn.Close()
	}
}

func (p *RabbitPublisher) PublishMetrics(ctx context.Context, metrics []NodeMetric) error {
	for _, m := range metrics {
		msg := struct {
			Type   string `json:"type"`  
			Node   string `json:"node"`  
			Metric struct {
				CPUUsageMilli            int64 `json:"cpu_usage_millicores"`
				MemoryUsageBytes         int64 `json:"memory_usage_bytes"`
				CPUCapacityMilli         int64 `json:"cpu_capacity_millicores"`
				MemoryCapacityBytes      int64 `json:"memory_capacity_bytes"`
				CPUAllocatableMilli      int64 `json:"cpu_allocatable_millicores"`
				MemoryAllocatableBytes   int64 `json:"memory_allocatable_bytes"`
			} `json:"metric"`
			Ts int64 `json:"ts"` 
		}{
			Type: "node_metric",
			Node: m.Name,
			Ts:   m.Timestamp.UnixNano(),
		}
		msg.Metric.CPUUsageMilli            = m.CPUUsage.MilliValue()
		msg.Metric.MemoryUsageBytes         = m.MemoryUsage.Value()
		msg.Metric.CPUCapacityMilli         = m.CPUCapacity.MilliValue()
		msg.Metric.MemoryCapacityBytes      = m.MemoryCapacity.Value()
		msg.Metric.CPUAllocatableMilli      = m.CPUAllocatable.MilliValue()
		msg.Metric.MemoryAllocatableBytes   = m.MemoryAllocatable.Value()

		body, _ := json.Marshal(msg)

		if err := p.channel.PublishWithContext(
			ctx, "", p.queueName, false, false,
			amqp.Publishing{
				ContentType:  "application/json",
				DeliveryMode: amqp.Persistent,
				Timestamp:    time.Now(),
				Body:         body,
			}); err != nil {
			return fmt.Errorf("publish: %w", err)
		}
	}
	return nil
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
