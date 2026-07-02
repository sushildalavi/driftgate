import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ApiService } from '../api.service';
import { ContractReviewRecord, EndpointRecord } from '../models';

@Component({
  standalone: true,
  imports: [RouterLink],
  templateUrl: './review.page.html',
  styleUrl: './shared.css',
})
export class ReviewPage {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);

  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly actionMessage = signal<string | null>(null);
  readonly endpoints = signal<EndpointRecord[]>([]);
  readonly selectedEndpointId = signal<string | null>(null);
  readonly reviews = signal<ContractReviewRecord[]>([]);
  readonly reviewLoading = signal(false);

  readonly selectedEndpoint = computed(
    () => this.endpoints().find((endpoint) => endpoint.id === this.selectedEndpointId()) ?? null,
  );
  readonly selectedReview = computed(() => this.reviews()[0] ?? null);

  constructor() {
    this.api
      .getRegistryOverview()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (registry) => {
          this.endpoints.set(registry.endpoints);
          this.loading.set(false);
          const firstEndpoint = registry.endpoints[0] ?? null;
          this.selectedEndpointId.set(firstEndpoint?.id ?? null);
          if (firstEndpoint) {
            this.loadReviews(firstEndpoint.id);
          }
        },
        error: () => {
          this.loading.set(false);
          this.errorMessage.set('Registry data could not be loaded. Start the runtime stack to inspect live reviews.');
        },
      });
  }

  selectEndpoint(endpointId: string): void {
    this.selectedEndpointId.set(endpointId);
    this.loadReviews(endpointId);
  }

  generateReview(): void {
    const endpointId = this.selectedEndpointId();
    if (!endpointId) {
      this.actionMessage.set('Select an endpoint first.');
      return;
    }
    this.reviewLoading.set(true);
    this.actionMessage.set('Generating contract review...');
    this.api
      .reviewContract(endpointId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (record) => {
          this.reviews.set([record, ...this.reviews().filter((item) => item.review_id !== record.review_id)]);
          this.actionMessage.set(`Review ${record.review_id} generated.`);
          this.reviewLoading.set(false);
        },
        error: (error) => {
          this.reviewLoading.set(false);
          this.actionMessage.set(error?.message ?? 'Review generation failed.');
        },
      });
  }

  trackById(_: number, item: { id?: string; review_id?: string }): string {
    return item.id ?? item.review_id ?? '';
  }

  private loadReviews(endpointId: string): void {
    this.reviewLoading.set(true);
    this.api
      .getContractReviews(endpointId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (reviews) => {
          this.reviews.set(reviews);
          this.reviewLoading.set(false);
        },
        error: (error) => {
          this.reviewLoading.set(false);
          this.actionMessage.set(error?.message ?? 'Could not load review history.');
        },
      });
  }
}
