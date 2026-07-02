import { AsyncPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService } from '../api.service';

@Component({
  standalone: true,
  imports: [AsyncPipe, RouterLink],
  templateUrl: './reliability.page.html',
  styleUrl: './shared.css',
})
export class ReliabilityPage {
  private readonly api = inject(ApiService);
  readonly dlq$ = this.api.getDlqEntries();
  readonly attempts$ = this.api.getDeliveryAttempts();
  readonly replayMessage = signal<string | null>(null);

  replay(dlqId: string): void {
    this.replayMessage.set(`Replaying ${dlqId}...`);
    this.api.replayDlqEntry(dlqId).subscribe({
      next: (result) => this.replayMessage.set(result.replayed ? `Replayed ${result.event_id}` : `Replay failed for ${result.event_id}`),
      error: (error) => this.replayMessage.set(error?.message ?? 'Replay failed'),
    });
  }
}
