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
    { title: 'Webhook ingress', detail: 'HMAC verification, idempotency, and request normalization at the edge.' },
    { title: 'Runtime guard', detail: 'Schema drift detection, payload snapshots, and runtime contract classification.' },
    { title: 'Event backends', detail: 'Azure Service Bus-compatible adapters with local no-op and Kafka paths.' },
    { title: 'Document store', detail: 'Mongo-first evidence store that can be adapted to Cosmos-compatible APIs.' },
    { title: 'Control room', detail: 'Angular console for governance, review, observability, and replay.' },
    { title: 'Benchmarks', detail: 'k6 profiles and artifact renderers keep proof tied to raw results.' },
  ];
}
