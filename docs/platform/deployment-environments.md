# Deployment Environments

## Current Profiles

`platform/assembly/env-matrix.yaml` is the platform-level matrix for environment and cluster behavior.

Initial profiles:

1. `local-k3s`
2. `orbstack-k3s-cn`
3. `prod-planned`

## Rules

1. Environment differences belong in profile files, not duplicated scripts.
2. Dev can auto-sync; production should remain review-gated.
3. Service map, smoke targets, public ingress, and release policy must be profile-driven.

## Secrets

Secrets are still externalized and must not be stored in this repository.
This directory only records references and expected runtime contracts.
