#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-microshop}"
RELEASE="${RELEASE:-microshop}"
MODE="${1:-helm}"

if [[ "${MODE}" == "--manifests" ]]; then
  kubectl apply -f k8s/base/namespace.yaml
  kubectl apply -f k8s/base/configmap.yaml
  kubectl apply -f k8s/base/secret.yaml
  kubectl apply -f k8s/base/redis.yaml
  kubectl apply -f k8s/services/
  echo "Applied raw manifests into namespace ${NAMESPACE}"
  exit 0
fi

kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1 || kubectl create namespace "${NAMESPACE}"
helm upgrade --install "${RELEASE}" ./helm/microshop --namespace "${NAMESPACE}"
echo "Helm release ${RELEASE} deployed into namespace ${NAMESPACE}"
