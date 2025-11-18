package main

import (
	"os"

	"k8s.io/component-base/cli"
	_ "k8s.io/component-base/logs/json/register"
	"github.com/karmada-io/karmada/cmd/scheduler/app"
	"github.com/karmada-io/karmada/pkg/scheduler/framework/plugins/sdi"
    signals "sigs.k8s.io/controller-runtime/pkg/manager/signals"
)

func main() {
	ctx := signals.SetupSignalHandler()
	cmd := app.NewSchedulerCommand(
		ctx,
		app.WithPlugin(sdi.Name, sdi.New),
	)
	os.Exit(cli.Run(cmd))
}
