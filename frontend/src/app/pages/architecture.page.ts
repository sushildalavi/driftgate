import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  standalone: true,
  imports: [RouterLink],
  templateUrl: './architecture.page.html',
  styleUrl: './shared.css',
})
export class ArchitecturePage {
  readonly layers = [
    { title: 'Angular 20 UI', detail: 'Operator control room for governance, review, observability, and evidence.' },
    { title: 'Node.js/Fastify webhook gateway', detail: 'HMAC verification, idempotency, and request normalization at the edge.' },
    { title: 'FastAPI runtime guard', detail: 'Schema drift detection, payload snapshots, and runtime contract classification.' },
    { title: 'PostgreSQL contract registry + outbox', detail: 'Stores contracts, versions, subscriptions, and reliable delivery state.' },
    { title: 'MongoDB raw payload / document history', detail: 'Preserves payload history, validation failures, diffs, and review artifacts.' },
    { title: 'LangGraph review workflow', detail: 'Grounded review decisions and migration notes from evidence.' },
    { title: 'Azure Service Bus-compatible delivery adapter', detail: 'Drift-event delivery abstraction for Azure-shaped infrastructure.' },
    { title: 'Prometheus / Grafana + k6', detail: 'Metrics, dashboards, and benchmark runs for repeatable verification.' },
  ];
}
