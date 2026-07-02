import { AsyncPipe, DecimalPipe, JsonPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { forkJoin, map, switchMap, tap } from 'rxjs';

import { ApiService } from '../api.service';
import { ContractReviewRecord } from '../models';

@Component({
  standalone: true,
  imports: [AsyncPipe, DecimalPipe, JsonPipe, RouterLink],
  templateUrl: './endpoint-detail.page.html',
  styleUrl: './shared.css',
})
export class EndpointDetailPage {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  readonly review = signal<ContractReviewRecord | null>(null);
  readonly reviewMessage = signal<string | null>(null);
  readonly reviewLoading = signal(false);
  readonly vm$ = this.route.paramMap.pipe(
    map((params) => params.get('id') ?? ''),
    tap(() => {
      this.review.set(null);
      this.reviewMessage.set(null);
      this.reviewLoading.set(false);
    }),
    switchMap((id) =>
      forkJoin({
        detail: this.api.getEndpointDetail(id),
        reviews: this.api.getContractReviews(id),
      }),
    ),
  );

  trackById(_: number, item: { id: string }): string {
    return item.id;
  }

  generateReview(endpointId: string): void {
    this.reviewLoading.set(true);
    this.reviewMessage.set('Generating contract review...');
    this.api.reviewContract(endpointId).subscribe({
      next: (record) => {
        this.review.set(record);
        this.reviewMessage.set(`Review ${record.review_id} generated`);
        this.reviewLoading.set(false);
      },
      error: (error) => {
        this.reviewMessage.set(error?.message ?? 'Review generation failed');
        this.reviewLoading.set(false);
      },
    });
  }

  copyText(text: string): void {
    void navigator.clipboard.writeText(text);
  }

  selectReview(reviews: ContractReviewRecord[]): ContractReviewRecord | null {
    return this.review() ?? reviews[0] ?? null;
  }
}
