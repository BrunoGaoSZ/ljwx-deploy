# Bid-MVP Factory Control Planes Plan (ljwx-deploy, refreshed on 2026-03-03)

## Phase 0 Inventory

### Existing
- Workflows exist under `.github/workflows/`:
  - `nightly-evidence.yml`
  - `nightly-auto-repair.yml`
  - `deploy-repo-gate.yml`
  - `build-promoter-image.yml`
- Evidence control plane exists:
  - `evidence/schema/evidence-record.schema.json`
  - `evidence/schema/evidence.schema.json`
  - `evidence/records/` (directory tracked)
  - `scripts/evidence/collect.py`
  - `scripts/evidence/validate.py`
  - `evidence/index.json`, `evidence/summary/latest.md`
- Pages dashboard source exists in both `pages/` and `site/` (needs consolidation decision).
- Release queue + promoter exists:
  - `release/queue.yaml`, `release/services.yaml`
  - `scripts/promoter/promote.py`, `scripts/promoter/deploy_promoter.py`, `scripts/promoter/validate_queue.py`
  - CronJob manifests: `infra/factory/deploy-promoter-cronjob.yaml`, `k8s/promoter/deploy-promoter-cronjob.yaml`
- Smoke loop exists:
  - `scripts/smoke/run_smoke.py`, `scripts/smoke/targets.json`
  - `infra/factory/smoke-runner-cronjob.yaml`
- Auto-repair loop exists:
  - `repairs/recipes.yaml`
  - `scripts/repair/run.sh`, `scripts/repair/run_repair.py`, `scripts/repair/diagnose.py`
  - orchestration docs/scripts: `infra/factory/INTEGRATION_RUN_ALL.md`, `scripts/factory/run_all_dev.sh`, `TEST.md`

### Current Gap / To Improve
- Two-cluster invariant hardening (required):
  - Same GitOps code must support both local server `k3s` and China mainland dev server `OrbStack k3s`.
  - Differences must be represented via overlays/values/env only, no forked logic or duplicated pipelines.
- Promoter implementation appears duplicated (`promote.py` and `deploy_promoter.py`):
  - choose one canonical entrypoint to avoid drift and behavioral mismatch.
- Queue state alignment:
  - ensure docs/code agree on `pending/promoted/failed/superseded` semantics and data placement.
- Pages source alignment:
  - choose one source directory (`pages/` or `site/`) and document workflow contract.
- Deploy gate hardening:
  - verify gate blocks unauthorized file changes and validates queue/evidence schemas deterministically.

### Existing promoter/test-runner/evidence/pages status
- Promoter: present.
- Test-runner/smoke runner: present.
- Evidence model/feed: present.
- Pages/gh-pages publishing: present.
- Conclusion: Phases 2-5 are largely implemented; next step is consistency hardening and elimination of drift.

## Planned File Changes (next deploy iterations)
- `scripts/promoter/*` (canonicalize single promoter path and behavior)
- `release/README.md`, `release/queue.yaml` (shape/field consistency)
- `.github/workflows/nightly-evidence.yml` + docs (single pages source contract)
- `docs/pages.md`, `docs/ops-runbook.md` (two-k3s same-code rule and runbook precision)
- `argocd-apps/` and/or `apps/*/overlays/*` (if overlay naming normalization is needed for dual k3s)

## Local Validation Commands
- `test -f PLAN.md && sed -n '1,260p' PLAN.md`
- `python3 scripts/evidence/validate.py`
- `python3 scripts/evidence/collect.py --out evidence/index.json --summary evidence/summary/latest.md`
- `python3 scripts/promoter/validate_queue.py --queue release/queue.yaml`
- `python3 scripts/promoter/promote.py --dry-run --skip-registry-check`
- `python3 scripts/smoke/run_smoke.py --dry-run`
- `python3 scripts/repair/diagnose.py --help`
- `python3 scripts/repair/run_repair.py --help`

## Commit Plan
- `phase0(deploy): refresh inventory plan`
- `phase3(deploy): promoter/queue canonicalization + dual-k3s overlay rule hardening`
- `phase4(deploy): smoke/evidence consistency hardening`
- `phase5(deploy): auto-repair determinism and gate tightening`
