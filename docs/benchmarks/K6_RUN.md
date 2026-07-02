# k6 Benchmark Runbook

This runbook keeps raw JSON as the source of truth. Markdown summaries should be regenerated from the JSON artifacts, not edited by hand.

## Command

```bash
python scripts/run_k6_benchmark.py \
  --script k6/track_profile.js \
  --name k6_25vus_10000req \
  --vus 25 \
  --total-requests 10000 \
  --track-url http://localhost:8302/track
```

## Notes
- The runner writes raw summary JSON, a sidecar state JSON, and a Markdown summary.
- Supported profile tiers are `25/50/100/200 VUs` with `5,000` requests each, plus the new `10K`, `25K`, `50K`, and `100K` request profiles when the runtime host can sustain them.
- For webhook failure injection validation, set `FAIL_WEBHOOK=true` and use failing consumer subscriptions.
- Do not claim benchmark metrics unless the JSON artifact came from an actual run.
