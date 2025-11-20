package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/metrics/pkg/client/clientset/versioned"

	metriccollector "sdi-scheduler/metric-collector/pkg/metric-collector"
)

func main() {
	log.Println("▶️  Metric-Collector starting…")

	// In-cluster K8s config
	cfg, err := rest.InClusterConfig()
	if err != nil {
		log.Fatalf("in-cluster config: %v", err)
	}

	clientset, err := kubernetes.NewForConfig(cfg)
	if err != nil {
		log.Fatalf("clientset: %v", err)
	}

	metricsClient, err := versioned.NewForConfig(cfg)
	if err != nil {
		log.Fatalf("metrics client: %v", err)
	}

	// RabbitMQ publisher
	pub, err := metriccollector.NewRabbitPublisher()
	if err != nil {
		log.Fatalf("rabbit publisher: %v", err)
	}
	defer pub.Close()

	collector := metriccollector.NewCollector(clientset, metricsClient)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	ticker := time.NewTicker(15 * time.Second)
	defer ticker.Stop()
	log.Println("✅  ready — collecting every 15 s")

	go func() {
		for {
			select {
			case <-ticker.C:
				metrics, err := collector.Collect(ctx)
				if err != nil {
					log.Printf("collect err: %v", err)
					continue
				}
				if len(metrics) == 0 {
					continue
				}
				if err := pub.PublishMetrics(ctx, metrics); err != nil {
					log.Printf("publish err: %v", err)
				} else {
					log.Printf("📤 published %d metrics", len(metrics))
				}
			case <-ctx.Done():
				return
			}
		}
	}()

	<-sigCh
	log.Println("⏹  shutdown signal — exiting")
}
