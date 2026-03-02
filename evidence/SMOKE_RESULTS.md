# Reading Smoke Results

Smoke results are written into each evidence record under `tests.smoke`:

- `tests.smoke.status`: `pass` or `fail`
- `tests.smoke.checkedAt`: UTC timestamp of the last smoke run
- `tests.smoke.details`: Argo sync/health and endpoint response summary

## Where It Appears on Dashboard

Open: `https://brunogaosz.github.io/ljwx-deploy/`

In the `Latest Records` table:

- `Smoke` column shows smoke status badge (`pass`/`fail`/`unknown`).
- `syncedAt` shows the promotion timestamp.

## Typical Investigation

1. Filter/find the affected service row.
2. Confirm `syncedAt` is recent for the expected rollout.
3. Inspect `Smoke` badge.
4. If `fail`, open record path and read `tests.smoke.details` for exact Argo/endpoint context.
