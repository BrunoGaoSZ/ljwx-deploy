#!/usr/bin/env bash
set -euo pipefail

CATALOG_PATH="${1:-factory/onboarding/services.catalog.yaml}"
MODE="${2:-apply}"
CLUSTER_BOOTSTRAP="${ONBOARD_CLUSTER_BOOTSTRAP:-true}"
NAMESPACE_PROFILES_PATH="${ONBOARD_NAMESPACE_PROFILES_PATH:-factory/onboarding/namespace-profiles.yaml}"
CAPABILITY_PROFILES_PATH="${ONBOARD_CAPABILITY_PROFILES_PATH:-factory/onboarding/capability-profiles.yaml}"
SERVICE_TEMPLATES_PATH="${ONBOARD_SERVICE_TEMPLATES_PATH:-factory/onboarding/service-templates.yaml}"
INGRESS_PROFILES_PATH="${ONBOARD_INGRESS_PROFILES_PATH:-factory/onboarding/ingress-profiles.yaml}"
CLUSTER_KUSTOMIZATION_PATH="${ONBOARD_CLUSTER_KUSTOMIZATION:-cluster/kustomization.yaml}"
DEPLOY_REPO_URL="${ONBOARD_DEPLOY_REPO_URL:-https://github.com/BrunoGaoSZ/ljwx-deploy.git}"
DEPLOY_REF="${ONBOARD_DEPLOY_REF:-main}"
FAIL_ON_DRIFT="${ONBOARD_FAIL_ON_DRIFT:-false}"

if [[ "$MODE" == "dry-run" ]]; then
  EXTRA_ARGS=()
  if [[ "$FAIL_ON_DRIFT" == "true" ]]; then
    EXTRA_ARGS+=(--fail-on-drift)
  fi
  uvx --with pyyaml python scripts/factory/onboard_services.py \
    --catalog "$CATALOG_PATH" \
    --namespace-profiles "$NAMESPACE_PROFILES_PATH" \
    --capability-profiles "$CAPABILITY_PROFILES_PATH" \
    --service-templates "$SERVICE_TEMPLATES_PATH" \
    --ingress-profiles "$INGRESS_PROFILES_PATH" \
    --cluster-bootstrap "$CLUSTER_BOOTSTRAP" \
    --cluster-kustomization "$CLUSTER_KUSTOMIZATION_PATH" \
    --deploy-repo-url "$DEPLOY_REPO_URL" \
    --deploy-ref "$DEPLOY_REF" \
    "${EXTRA_ARGS[@]}" \
    --dry-run
else
  uvx --with pyyaml python scripts/factory/onboard_services.py \
    --catalog "$CATALOG_PATH" \
    --namespace-profiles "$NAMESPACE_PROFILES_PATH" \
    --capability-profiles "$CAPABILITY_PROFILES_PATH" \
    --service-templates "$SERVICE_TEMPLATES_PATH" \
    --ingress-profiles "$INGRESS_PROFILES_PATH" \
    --cluster-bootstrap "$CLUSTER_BOOTSTRAP" \
    --cluster-kustomization "$CLUSTER_KUSTOMIZATION_PATH" \
    --deploy-repo-url "$DEPLOY_REPO_URL" \
    --deploy-ref "$DEPLOY_REF"
fi
