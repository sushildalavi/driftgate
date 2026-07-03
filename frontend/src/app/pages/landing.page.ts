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
      description: 'Run the stack in Docker while keeping Azure-compatible delivery and MongoDB history available locally.',
    },
  ];

  readonly workflow = [
    { title: 'Angular 20 UI', detail: 'Operator console for registry, review, observability, and benchmark evidence.' },
    { title: 'Node.js/Fastify gateway', detail: 'HMAC verification, idempotency checks, and normalized webhook capture.' },
    { title: 'FastAPI runtime guard', detail: 'Tracks live payloads, computes drift, and writes runtime evidence.' },
    { title: 'PostgreSQL registry + outbox', detail: 'Stores contracts, versions, subscriptions, and delivery state.' },
    { title: 'MongoDB document history', detail: 'Persists raw payloads, diffs, validation errors, and review artifacts.' },
    { title: 'LangGraph review flow', detail: 'Grounded review produces migration notes and delivery decisions.' },
    { title: 'Azure Service Bus adapter', detail: 'Delivers drift events through an Azure-compatible sender abstraction.' },
    { title: 'Prometheus / Grafana + k6', detail: 'Surfaces metrics and benchmark evidence for operator verification.' },
  ];

  readonly featureCards = [
    'Angular 20 UI',
    'Node.js/Fastify gateway',
    'HMAC webhook verification',
    'Idempotency keys',
    'Schema drift detection',
    'Severity classification',
    'PostgreSQL registry + outbox',
    'MongoDB payload history',
    'LangGraph review',
    'DLQ replay',
    'Prometheus/Grafana metrics',
    'k6 benchmark explorer',
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
      title: 'MongoDB history',
      value: 'Live',
      detail: 'Raw payload captures, validation failures, and review evidence are persisted in MongoDB.',
    },
    {
      title: 'Metrics and load',
      value: 'Live',
      detail: 'Prometheus, Grafana, and k6 artifacts provide operational telemetry and benchmark proof.',
    },
  ];

  readonly architectureNodes = [
    {
      title: 'Angular 20 UI',
      detail: 'Operator workspace for registry, diffs, review, observability, and benchmark evidence.',
    },
    {
      title: 'Node.js/Fastify webhook gateway',
      detail: 'HMAC verification, idempotency handling, and normalized event forwarding.',
    },
    {
      title: 'FastAPI runtime guard',
      detail: 'Tracks live payloads, computes drift, and orchestrates review-ready evidence.',
    },
    {
      title: 'PostgreSQL contract registry + outbox',
      detail: 'Stores endpoints, versions, subscriptions, and reliable delivery state.',
    },
    {
      title: 'MongoDB raw payload / document history',
      detail: 'Stores raw payload documents, validation errors, diffs, and review artifacts.',
    },
    {
      title: 'LangGraph review workflow',
      detail: 'Produces grounded contract decisions and migration notes from evidence.',
    },
    {
      title: 'Azure Service Bus-compatible delivery adapter',
      detail: 'Abstracts drift-event delivery without forcing a cloud dependency.',
    },
    {
      title: 'Prometheus / Grafana + k6',
      detail: 'Surfaces metrics, dashboards, and benchmark evidence in one loop.',
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
