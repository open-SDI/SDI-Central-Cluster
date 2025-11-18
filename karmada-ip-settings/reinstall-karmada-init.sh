#!/bin/bash

sudo karmadactl deinit

sudo karmadactl init \
  --kubeconfig /root/.kube-config \
  --karmada-apiserver-advertise-address=<IP번호>
