import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  standalone: true,
  imports: [RouterLink],
  templateUrl: './benchmark.page.html',
  styleUrl: './shared.css',
})
export class BenchmarkPage {
  readonly tiers = [
    { requests: '10K', vus: '25', label: 'smoke-capacity', note: 'Quick verification of the runtime guard hot path.' },
    { requests: '25K', vus: '25', label: 'baseline', note: 'Low-concurrency throughput with stable payload mix.' },
    { requests: '50K', vus: '50', label: 'mid-tier', note: 'Richer contention profile for DB and outbox writes.' },
    { requests: '100K', vus: '100', label: 'stress target', note: 'Feasible next step when the local stack is warmed.' },
    { requests: '250K', vus: '200', label: 'upper bound', note: 'Stretch target for the same benchmark profile.' },
  ];

  readonly signals = [
    'Total requests',
    'Throughput',
    'p50 / p95 / p99 latency',
    'Failure rate',
    'Drift rows created',
    'Outbox and DLQ rows',
    'Duplicate idempotency keys rejected',
    'Webhook delivery attempts',
    'DB state snapshot',
    'Metrics snapshot',
  ];
}
