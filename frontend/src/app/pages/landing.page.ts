import { Component, DestroyRef, inject, signal } from '@angular/core';
import { KeyValuePipe } from '@angular/common';
import { RouterLink } from '@angular/router';

import { ApiService, OverviewBundle } from '../api.service';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

@Component({
  standalone: true,
  imports: [KeyValuePipe, RouterLink],
  templateUrl: './landing.page.html',
  styleUrls: ['./landing.page.css', './shared.css'],
})
export class LandingPage {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);

  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly overview = signal<OverviewBundle | null>(null);
  readonly activeDemo = signal(0);

  readonly problemCards = [
    {
      title: 'Schema drift breaks consumers',
      description: 'Breaking fields, enum contractions, and type changes need visible evidence before rollout.',
    },
    {
      title: 'Webhook retries are opaque',
      description: 'Delivery attempts, DLQ entries, and replay outcomes should be inspectable from one console.',
    },
    {
      title: 'Review should be grounded',
      description: 'Contract decisions need payloads, diffs, validation failures, and subscription context.',
    },
    {
      title: 'Governance must stay local-first',
      description: 'Run the stack in Docker and keep Azure Service Bus and Cosmos compatibility optional.',
    },
  ];

  readonly workflow = [
    { title: 'Webhook Gateway', detail: 'HMAC verification, idempotency checks, and normalized capture.' },
    { title: 'Runtime Validation', detail: 'FastAPI runtime records snapshots, diffs, DLQ, and replay artifacts.' },
    { title: 'PostgreSQL Metadata', detail: 'Registry, versions, subscriptions, and delivery history.' },
    { title: 'MongoDB Document Store', detail: 'Payload, diff, and review evidence with Cosmos compatibility.' },
    { title: 'Angular Review Console', detail: 'Operational view for schema risk and contract review.' },
    { title: 'DLQ / Replay', detail: 'Recover failed deliveries with a clear audit trail.' },
  ];

  readonly featureCards = [
    'HMAC webhook verification',
    'Idempotency keys',
    'Schema drift detection',
    'Severity classification',
    'Payload and diff history',
    'DLQ replay',
    'Contract review',
    'Benchmark explorer',
    'Observability surface',
    'Azure-compatible event backend',
  ];

  readonly demoCards = [
    {
      label: 'Schema diff',
      title: 'Breaking contract change',
      severity: 'breaking',
      copy: 'A required field disappears, the diff view highlights the break, and the review flow keeps the evidence attached.',
    },
    {
      label: 'Delivery path',
      title: 'Webhook retry lane',
      severity: 'risky',
      copy: 'HMAC ingress, retry attempts, and the webhook DLQ stay visible from a single operator console.',
    },
    {
      label: 'Replay lane',
      title: 'DLQ recovery',
      severity: 'risky',
      copy: 'Replay actions are explicit, audited, and separated from drift-event publishing failures.',
    },
    {
      label: 'Severity pulse',
      title: 'Risk classification',
      severity: 'compatible',
      copy: 'Safe, risky, and breaking states are surfaced with clear badges and severity-aware routing.',
    },
    {
      label: 'Evidence graph',
      title: 'Grounded review',
      severity: 'review',
      copy: 'Schema diffs, payload snapshots, validation errors, subscriptions, and DLQ rows all feed the review.',
    },
  ];

  readonly proofCards = [
    {
      title: 'API governance',
      value: 'Live',
      detail: 'Registry, version history, subscriptions, and schema diffs are wired through the runtime and monitor.',
    },
    {
      title: 'Runtime reliability',
      value: 'Live',
      detail: 'HMAC ingress, transactional outbox, webhook DLQ, and drift-event DLQ are implemented separately.',
    },
    {
      title: 'Azure compatibility',
      value: 'Ready',
      detail: 'Azure Service Bus and Cosmos-style adapters are configurable without claiming deployment.',
    },
    {
      title: 'Load validation',
      value: 'Documented',
      detail: 'k6 scripts and reproducible benchmark exports are generated from raw run output.',
    },
  ];

  readonly architectureNodes = [
    {
      title: 'Gateway ingress',
      detail: 'HMAC verification, idempotency handling, and normalized event forwarding.',
    },
    {
      title: 'Runtime API',
      detail: 'FastAPI contract tracking, drift capture, contract review, and replay orchestration.',
    },
    {
      title: 'Metadata store',
      detail: 'PostgreSQL stores endpoints, snapshots, delivery attempts, subscriptions, and DLQs.',
    },
    {
      title: 'Document store',
      detail: 'MongoDB / Cosmos-compatible evidence store for payload snapshots and review artifacts.',
    },
    {
      title: 'Angular console',
      detail: 'Enterprise-style operator UI for governance, reliability, and replay workflows.',
    },
  ];

  constructor() {
    this.api
      .getOverview()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (overview) => {
          this.overview.set(overview);
          this.loading.set(false);
          this.errorMessage.set(null);
        },
        error: () => {
          this.loading.set(false);
          this.errorMessage.set('Live runtime data is unavailable right now. The seeded demo below still shows the product flow.');
        },
      });
  }

  selectDemo(index: number): void {
    this.activeDemo.set(index);
  }

  currentDemo() {
    return this.demoCards[this.activeDemo()] ?? this.demoCards[0];
  }
}
