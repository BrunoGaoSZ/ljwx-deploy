# Run-all Integration (Dev)

This flow supports the required sequence:

`commit -> PR -> wait checks -> auto-fix -> recheck -> merge (dev)`

## Scripted Flow

Use:

```bash
bash scripts/factory/run_all_dev.sh
```

The script will:

1. Push current feature branch.
2. Create (or reuse) PR against `main`.
3. Wait for check results.
4. On failure, run `scripts/repair/diagnose.py` (local log + `gh pr checks`) and `scripts/repair/run.sh` for deterministic repair.
5. Commit/push auto-fix changes.
6. Re-wait checks until success or attempts exhausted.
7. Merge PR automatically on success.

## Fail-after-N Behavior

When attempts are exhausted, auto-repair writes failure summary under `.factory/repair/.../failure-summary.md` and opens an issue (if token permissions allow) containing:

- minimal repro command
- attempt logs
- truncated last check output
- timestamps and context

## Recipe Source

- Canonical deterministic recipe file: `repairs/recipes.yaml`
