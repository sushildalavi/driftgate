import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';

import { ApiService } from './api.service';

describe('ApiService', () => {
  let service: ApiService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), ApiService],
    });
    service = TestBed.inject(ApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('posts contract review requests', () => {
    service.reviewContract('endpoint-123').subscribe((response) => {
      expect(response.review.decision).toBe('approve');
    });

    const req = httpMock.expectOne('http://localhost:8018/api/v1/ai/contract-review');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({
      endpoint_id: 'endpoint-123',
      evidence_limit: 5,
      review_limit: 10,
    });
    req.flush({
      review_id: 'review-1',
      endpoint_id: 'endpoint-123',
      endpoint_name: 'shop POST /webhooks/shop',
      provider: 'fake',
      created_at: '2026-07-02T00:00:00Z',
      latency_seconds: 0.1,
      evidence_summary: 'safe baseline',
      consumer_impact: 'No active consumers',
      context: {
        endpoint_id: 'endpoint-123',
        endpoint_name: 'shop POST /webhooks/shop',
        namespace: 'gateway',
        service_name: 'shop',
        http_method: 'POST',
        route_path: '/webhooks/shop',
        schema_diffs: [],
        payload_snapshots: [],
        validation_failures: [],
        dlq_entries: [],
        delivery_attempts: [],
        subscriptions: [],
        drift_violations: [],
        notes: [],
        insufficient_evidence: false,
      },
      review: {
        decision: 'approve',
        severity: 'compatible',
        summary: 'Compatible',
        consumer_impact: 'No active consumers',
        evidence: ['[snapshot:1] safe baseline'],
        recommended_fixes: [],
        migration_note: 'No migration required.',
        review_comment: 'ok',
        confidence: 0.9,
        insufficient_evidence: false,
      },
    });
  });

  it('fetches contract review history', () => {
    service.getContractReviews('endpoint-123').subscribe((response) => {
      expect(response.length).toBe(1);
    });

    const req = httpMock.expectOne((request) => {
      return (
        request.url === 'http://localhost:8018/api/v1/ai/contract-reviews' &&
        request.params.get('endpoint_id') === 'endpoint-123' &&
        request.params.get('limit') === '10'
      );
    });
    expect(req.request.method).toBe('GET');
    req.flush([
      {
        review_id: 'review-1',
        endpoint_id: 'endpoint-123',
        endpoint_name: 'shop POST /webhooks/shop',
        provider: 'fake',
        created_at: '2026-07-02T00:00:00Z',
        latency_seconds: 0.1,
        evidence_summary: 'safe baseline',
        consumer_impact: 'No active consumers',
        context: {
          endpoint_id: 'endpoint-123',
          endpoint_name: 'shop POST /webhooks/shop',
          namespace: 'gateway',
          service_name: 'shop',
          http_method: 'POST',
          route_path: '/webhooks/shop',
          schema_diffs: [],
          payload_snapshots: [],
          validation_failures: [],
          dlq_entries: [],
          delivery_attempts: [],
          subscriptions: [],
          drift_violations: [],
          notes: [],
          insufficient_evidence: false,
        },
        review: {
          decision: 'approve',
          severity: 'compatible',
          summary: 'Compatible',
          consumer_impact: 'No active consumers',
          evidence: ['[snapshot:1] safe baseline'],
          recommended_fixes: [],
          migration_note: 'No migration required.',
          review_comment: 'ok',
          confidence: 0.9,
          insufficient_evidence: false,
        },
      },
    ]);
  });
});
