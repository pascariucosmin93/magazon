#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-microshop}"
RELEASE="${RELEASE:-microshop}"
TIMEOUT="${TIMEOUT:-5m}"
KEY_SERVICES="auth-service frontend"

# ── Secret pre-flight check ───────────────────────────────────────────────────
# deploy.sh manages secrets directly (secret.manage=true).
# For ArgoCD/GitOps, pre-create the secret manually and leave secret.manage=false.

if [[ -z "${POSTGRES_PASSWORD:-}" || -z "${JWT_SECRET:-}" ]]; then
  echo "ERROR: POSTGRES_PASSWORD and JWT_SECRET must be set as environment variables." >&2
  echo "  export POSTGRES_PASSWORD='...'" >&2
  echo "  export JWT_SECRET='...'" >&2
  exit 1
fi

# ── Tool version checks ──────────────────────────────────────────────────────

check_tool() {
  if ! command -v "$1" &>/dev/null; then
    echo "ERROR: $1 is not installed or not in PATH" >&2
    exit 1
  fi
}

check_tool kubectl
check_tool helm

KUBECTL_VER=$(kubectl version --client --output=json 2>/dev/null | python3 -c "import sys,json; v=json.load(sys.stdin)['clientVersion']; print(f\"{v['major']}.{v['minor']}\")" 2>/dev/null || echo "unknown")
HELM_VER=$(helm version --short 2>/dev/null | grep -oE 'v[0-9]+\.[0-9]+' | head -1 || echo "unknown")
echo "Using kubectl ${KUBECTL_VER}, helm ${HELM_VER}"

# ── Namespace ────────────────────────────────────────────────────────────────

kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1 || kubectl create namespace "${NAMESPACE}"

# ── Helm dry-run ─────────────────────────────────────────────────────────────

echo "Running Helm dry-run..."
helm upgrade --install "${RELEASE}" ./helm/microshop \
  --namespace "${NAMESPACE}" \
  --set secret.manage=true \
  --set "secret.postgresPassword=${POSTGRES_PASSWORD}" \
  --set "secret.jwtSecret=${JWT_SECRET}" \
  --dry-run \
  "$@" \
  >/dev/null
echo "Dry-run passed."

# ── Deploy ───────────────────────────────────────────────────────────────────

echo "Deploying release ${RELEASE} into namespace ${NAMESPACE}..."
helm upgrade --install "${RELEASE}" ./helm/microshop \
  --namespace "${NAMESPACE}" \
  --set secret.manage=true \
  --set "secret.postgresPassword=${POSTGRES_PASSWORD}" \
  --set "secret.jwtSecret=${JWT_SECRET}" \
  --timeout "${TIMEOUT}" \
  --wait \
  "$@"

# ── Rollout wait ─────────────────────────────────────────────────────────────

wait_for_rollout() {
  local svc="$1"
  echo "Waiting for rollout: ${svc}..."
  if ! kubectl rollout status deployment/"${svc}" \
      --namespace "${NAMESPACE}" \
      --timeout "${TIMEOUT}" 2>&1; then
    echo "ERROR: Rollout failed for ${svc}" >&2
    echo "--- Pod describe ---" >&2
    kubectl describe pods -n "${NAMESPACE}" -l "app=${svc}" >&2 || true
    echo "--- Recent logs ---" >&2
    kubectl logs -n "${NAMESPACE}" -l "app=${svc}" --tail=50 --previous 2>/dev/null || \
      kubectl logs -n "${NAMESPACE}" -l "app=${svc}" --tail=50 2>/dev/null || true
    return 1
  fi
}

failed=0
for svc in ${KEY_SERVICES}; do
  wait_for_rollout "${svc}" || failed=1
done

if [[ "${failed}" -eq 1 ]]; then
  echo "ERROR: One or more key services failed to roll out." >&2
  exit 1
fi

echo "Helm release ${RELEASE} deployed successfully into namespace ${NAMESPACE}."
kubectl get pods -n "${NAMESPACE}"
