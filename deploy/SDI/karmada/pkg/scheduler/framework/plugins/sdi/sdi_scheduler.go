package sdi

import (
	"context"
	"fmt"
	"os"
	"strconv"

	clusterv1alpha1 "github.com/karmada-io/karmada/pkg/apis/cluster/v1alpha1"
	workv1alpha2 "github.com/karmada-io/karmada/pkg/apis/work/v1alpha2"
	"github.com/karmada-io/karmada/pkg/scheduler/framework"
)

type ScoreValues struct {
	Accuracy int
	Latency  int
	Energy   int
}

type ALE struct {
	Accuracy struct {
		TargetAccuracy struct {
			Value int `json:"value" yaml:"value"`
		} `json:"targetAccuracy" yaml:"targetAccuracy"`
		ModelType                string `json:"modelType" yaml:"modelType"`
		ComputeIntensityTFLOPS   int    `json:"computeIntensityTFLOPS" yaml:"computeIntensityTFLOPS"`
	} `json:"accuracy" yaml:",inline"`

	Latency struct {
		Budget struct {
			P95 int `json:"p95" yaml:"p95"`
		} `json:"budget" yaml:"budget"`
		Class           string `json:"class" yaml:"class"`
		LatencyBudgetMs int    `json:"latencyBudgetMs" yaml:"latencyBudgetMs"`
		Region          string `json:"region" yaml:"region"`
	} `json:"latency" yaml:",inline"`

	Energy struct {
		PowerBudgetWatt  int    `json:"powerBudgetWatt"  yaml:"powerBudgetWatt"`
		EnergyClass      string `json:"energyClass"      yaml:"energyClass"`
		RuntimeWindowSec int    `json:"runtimeWindowSec" yaml:"runtimeWindowSec"`
	} `json:"energy" yaml:",inline"`
}

const Name = "SDIScheduler"

type Strategy interface {
	Name() string
	Filter(ctx context.Context, bs *workv1alpha2.ResourceBindingSpec, cl *clusterv1alpha1.Cluster, ale *ALE) framework.Code
	Score(ctx context.Context, bs *workv1alpha2.ResourceBindingSpec, cl *clusterv1alpha1.Cluster, ale *ALE) (int64, error)
}

type SDIPlugin struct {
	strategies map[string]Strategy

	scores *ScoreValues
}

func (p *SDIPlugin) Name() string { return Name }

func New() (framework.Plugin, error) {
	p := &SDIPlugin{
		strategies: map[string]Strategy{
			"intent":  &IntentDriven{},
			"predict": &PredictiveContext{},
			"swarm":   &CollaborativeSwarm{},
		},
	}

	if s, err := fetchScores(context.Background()); err == nil {
		p.scores = s
	} else {
		fmt.Printf("[SDI] analysis engine fetch failed: %v\n", err)
	}

	return p, nil
}

func (p *SDIPlugin) pick(bs *workv1alpha2.ResourceBindingSpec) Strategy {
	name := "intent"
	if bs != nil && bs.Placement != nil && bs.Placement.ClusterAffinities != nil {
	}
	if s, ok := p.strategies[name]; ok {
		return s
	}
	return p.strategies["intent"]
}

func (p *SDIPlugin) parseALE(ctx context.Context, bs *workv1alpha2.ResourceBindingSpec) (*ALE, error) {
	ale := &ALE{}

	if v := getEnv("MALE_ACCURACY"); v != "" {
		if iv, err := strconv.Atoi(v); err == nil {
			ale.Accuracy.TargetAccuracy.Value = iv
		}
	}
	if v := getEnv("MALE_LATENCY"); v != "" {
		if iv, err := strconv.Atoi(v); err == nil {
			ale.Latency.Budget.P95 = iv
			ale.Latency.LatencyBudgetMs = iv
		}
	}
	if v := getEnv("MALE_ENERGY"); v != "" {
		if iv, err := strconv.Atoi(v); err == nil {
			ale.Energy.PowerBudgetWatt = iv
		}
	}
	if v := getEnv("SERVICE_TYPE"); v != "" {
		ale.Accuracy.ModelType = v
	}

	if p.scores != nil {
		ale.Accuracy.TargetAccuracy.Value = p.scores.Accuracy
		ale.Latency.Budget.P95 = p.scores.Latency
		ale.Latency.LatencyBudgetMs = p.scores.Latency
		ale.Energy.PowerBudgetWatt = p.scores.Energy
	}

	return ale, nil
}

func (p *SDIPlugin) Filter(
	ctx context.Context,
	bs *workv1alpha2.ResourceBindingSpec,
	cl *clusterv1alpha1.Cluster,
) *framework.Result {
	ale, err := p.parseALE(ctx, bs)
	if err != nil {
		return framework.AsResult(err)
	}
	code := p.pick(bs).Filter(ctx, bs, cl, ale)
	return framework.NewResult(code)
}

func (p *SDIPlugin) Score(
	ctx context.Context,
	bs *workv1alpha2.ResourceBindingSpec,
	cl *clusterv1alpha1.Cluster,
) (int64, *framework.Result) {
	ale, err := p.parseALE(ctx, bs)
	if err != nil {
		return 0, framework.AsResult(err)
	}
	score, err := p.pick(bs).Score(ctx, bs, cl, ale)
	if err != nil {
		return 0, framework.AsResult(err)
	}
	return score, nil
}

func getEnv(k string) string {
	v := ""
	if vv, ok := lookupEnv(k); ok {
		v = vv
	}
	return v
}

var lookupEnv = func(k string) (string, bool) { return syscallLookupEnv(k) }

func syscallLookupEnv(k string) (string, bool) {
	return getenv(k)
}

func getenv(k string) (string, bool) {
	return osLookupEnv(k)
}

var osLookupEnv = func(k string) (string, bool) { return os.LookupEnv(k) } // go1.21+: strconv.LookupEnv 없음이면 os.LookupEnv 사용
