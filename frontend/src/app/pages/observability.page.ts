import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  standalone: true,
  imports: [RouterLink],
  templateUrl: './observability.page.html',
  styleUrl: './shared.css',
})
export class ObservabilityPage {
  readonly endpoints = [
    { label: 'Backend health', url: 'http://localhost:8301/health', detail: 'Monitor API readiness probe.' },
    { label: 'Runtime metrics', url: 'http://localhost:8302/api/v1/metrics', detail: 'JSON metrics used by the console.' },
    { label: 'Gateway health', url: 'http://localhost:8303/health', detail: 'Webhook ingress status.' },
    { label: 'Prometheus', url: 'http://localhost:9301', detail: 'Metrics scrape endpoint when enabled.' },
    { label: 'Grafana', url: 'http://localhost:3301', detail: 'Dashboard surface when provisioned.' },
  ];

  readonly signals = [
    'contract_review_count',
    'contract_review_insufficient_evidence_count',
    'drift_event_dlq_count',
    'webhook_delivery_dlq_count',
    'webhook_delivery_attempts_count',
    'drift_detection_latency_seconds',
  ];
}
