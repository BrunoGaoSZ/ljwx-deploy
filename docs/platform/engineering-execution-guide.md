# Engineering Execution Guide

## Change Types

| Change type | Primary files |
| --- | --- |
| routing behavior | `platform/routing/`, `platform/contracts/`, `release/platform-version.yaml` |
| knowledge publication | `platform/knowledge/`, knowledge source repos, publish workflow |
| capability ownership | `platform/assembly/capabilities.yaml`, `platform/contracts/service-capability-map.yaml` |
| deployment topology | `apps/`, `cluster/`, `argocd-apps/`, `release/` |

## Required PR Contents

Every platform PR should include:

1. scope and impacted environments
2. changed source-of-truth files
3. rollback method
4. verification evidence
5. follow-up tasks if the change is staged

## Minimum Review Standard

1. platform config and runtime behavior must match
2. no component should silently gain a new responsibility boundary
3. route and capability changes must remain explainable from Git
