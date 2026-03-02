# Reading Smoke Results

Smoke results are written into each evidence record under the `smoke` field:

- `smoke.status`: `pass` or `fail`
- `smoke.checked_at`: UTC timestamp of the last smoke run
- `smoke.details`: Argo sync/health and endpoint response summary

## Where It Appears on Dashboard

Open: `https://brunogaosz.github.io/ljwx-deploy/`

In the `Latest Records` table:

- `Promotion` column shows queue promotion status.
- `Smoke` column shows smoke status badge (`pass`/`fail`/`unknown`).
- `Updated` shows when the record was last changed.

## Typical Investigation

1. Filter/find the affected service row.
2. Confirm `Promotion` is `promoted`.
3. Inspect `Smoke` badge.
4. If `fail`, open record path and read `smoke.details` for exact Argo/endpoint context.
