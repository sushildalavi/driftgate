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
    'Azure-ready event backend',
  ];

  readonly demoCards = [
    {
      label: 'Seeded demo',
      title: 'Breaking schema diff',
      severity: 'breaking',
      copy: 'Removed required `price` and tightened a consumer-facing payload.',
    },
    {
      label: 'Seeded demo',
      title: 'Risky change',
      severity: 'risky',
      copy: 'Nullable field became required after a service contract update.',
    },
    {
      label: 'Seeded demo',
      title: 'Failed delivery',
      severity: 'risky',
      copy: 'Delivery retries accumulated and the event moved to the DLQ.',
    },
    {
      label: 'Seeded demo',
      title: 'Replay item',
      severity: 'compatible',
      copy: 'Replay completed after the downstream issue was cleared.',
    },
    {
      label: 'Seeded demo',
      title: 'Contract review',
      severity: 'review',
      copy: 'Grounded review summarizes evidence, migration note, and consumer impact.',
    },
  ];

  readonly verificationFacts = [
    {
      title: 'Backend pytest',
      value: '59 passed',
      detail: 'Current workspace backend and runtime test run.',
    },
    {
      title: 'Angular lint',
      value: 'passed',
      detail: 'Front-end linting completed successfully.',
    },
    {
      title: 'Angular build',
      value: 'passed',
      detail: 'Production build completed successfully.',
    },
    {
      title: 'Angular tests',
      value: '4 passed',
      detail: 'ChromeHeadless component and service tests.',
    },
  ];

  readonly architectureNodes = [
    {
      title: 'Gateway',
      detail: 'Ingress, verification, request normalization, and event publication.',
    },
    {
      title: 'Runtime API',
      detail: 'FastAPI orchestration, schema drift capture, and contract review.',
    },
    {
      title: 'Metadata store',
      detail: 'PostgreSQL endpoint registry, versions, subscriptions, and history.',
    },
    {
      title: 'Document store',
      detail: 'MongoDB / Cosmos-compatible evidence store for payload and review artifacts.',
    },
    {
      title: 'Angular console',
      detail: 'Operator UI for governance, reliability, and review workflows.',
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
