# GitHub Project Plan

## Purpose

Use GitHub Milestones, Epics, and Issues to plan platform work with clear ownership, scheduling, evidence, and rollback.

## Milestones

- Define a dated delivery checkpoint or platform outcome.
- Group epics that must be completed together.
- Carry exit criteria that can be verified from GitHub, manifests, and runtime evidence.

## Epics

- Represent one cross-repo capability slice under a milestone.
- Link the affected repos, contracts, and operating procedures.
- Decompose into issues that can be reviewed and rolled back independently.

## Issues

- Represent the smallest reviewable execution unit.
- Change one coherent behavior, contract, or operational path.
- Always include acceptance, evidence, and rollback before moving to done.

## Priority

- `P0`: production blocker, security issue, or same-day delivery requirement.
- `P1`: current-week delivery target with direct dependency on active milestone work.
- `P2`: planned follow-up work that should land in the next scheduled wave.
- `P3`: backlog or optimization work without immediate release pressure.

## Week

- Use `YYYY-Www` format, for example `2026-W10`.
- Re-evaluate the week whenever dependencies or scope change.

## Dependencies

- List blocking issues, PRs, repos, manifests, or environment gates.
- Make blockers explicit enough that another engineer can trace them without oral context.

## Acceptance

- Define observable done conditions, not implementation intent.
- Prefer checks such as manifest diff merged, Argo sync healthy, smoke test pass, or contract updated.

## Evidence

- Attach the proof required to close the item.
- Typical evidence includes PR links, screenshots, command output, ArgoCD state, and smoke-test results.

## Rollback

- Document the exact revert path before execution starts.
- Include the repo or manifest to revert and the verification step after rollback.

## Recommended Planning Table

| Milestone | Epic | Issue | Priority | Week | Dependencies | Acceptance | Evidence | Rollback |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Platform routing baseline | Shared ingress behavior | Add platform redirect middleware to affected app overlay | P1 | 2026-W10 | ingress profile update, service PR | dev ingress smoke passes and docs updated | PR link, sync result, curl output | revert PR, resync app, rerun smoke |

## Operating Rules

1. Every execution issue should belong to one epic and one milestone.
2. Priority and week should be reviewed together; stale scheduling is a planning bug.
3. Acceptance and evidence should be specific enough for async review.
4. Rollback should be executable by an on-call engineer without extra explanation.
