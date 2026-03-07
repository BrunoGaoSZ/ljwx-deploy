# Platform Rollback

## Scope

Use this runbook when a platform release changes runtime behavior and must be reverted.

## Inputs

1. target `platform_version`
2. affected services
3. reason for rollback
4. verification owner

## Steps

1. identify the last known-good `release/platform-version.yaml`
2. re-enqueue last known-good image digests where required
3. restore route, capability, and knowledge config refs
4. merge or revert via PR
5. wait for Argo `Synced/Healthy`
6. run smoke and record evidence

## Evidence

- rollback PR
- Argo health snapshot
- smoke result
- updated evidence record
