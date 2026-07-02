import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { forkJoin, Observable } from 'rxjs';

import {
  ContractReviewRecord,
  DeliveryAttempt,
  DiffRecord,
  DlqEntry,
  DriftEventDlqEntry,
  DriftEventReplayResult,
  DocumentArtifact,
  EndpointRecord,
  MonitorMetrics,
  ReplayResult,
  SnapshotRecord,
  SubscriptionRecord,
} from './models';

export interface OverviewBundle {
  metrics: MonitorMetrics;
  endpoints: EndpointRecord[];
  diffs: DiffRecord[];
  dlq: DlqEntry[];
  attempts: DeliveryAttempt[];
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly monitorBaseUrl = 'http://localhost:8301';
  private readonly runtimeBaseUrl = 'http://localhost:8302';

  private readonly http = inject(HttpClient);

  getOverview(): Observable<OverviewBundle> {
    return forkJoin({
      metrics: this.getMetrics(),
      endpoints: this.getEndpoints(),
      diffs: this.getRecentDiffs(),
      dlq: this.getDlqEntries(),
      attempts: this.getDeliveryAttempts(),
    });
  }

  getMetrics(): Observable<MonitorMetrics> {
    return this.http.get<MonitorMetrics>(`${this.runtimeBaseUrl}/api/v1/metrics`);
  }

  reviewContract(endpointId: string, evidenceLimit = 5, reviewLimit = 10): Observable<ContractReviewRecord> {
    return this.http.post<ContractReviewRecord>(`${this.runtimeBaseUrl}/api/v1/ai/contract-review`, {
      endpoint_id: endpointId,
      evidence_limit: evidenceLimit,
      review_limit: reviewLimit,
    });
  }

  getContractReviews(endpointId: string, limit = 10): Observable<ContractReviewRecord[]> {
    return this.http.get<ContractReviewRecord[]>(`${this.runtimeBaseUrl}/api/v1/ai/contract-reviews`, {
      params: { endpoint_id: endpointId, limit },
    });
  }

  getEndpoints(): Observable<EndpointRecord[]> {
    return this.http.get<EndpointRecord[]>(`${this.monitorBaseUrl}/api/endpoints`);
  }

  getEndpoint(endpointId: string): Observable<EndpointRecord> {
    return this.http.get<EndpointRecord>(`${this.monitorBaseUrl}/api/endpoints/${endpointId}`);
  }

  getEndpointSnapshots(endpointId: string): Observable<SnapshotRecord[]> {
    return this.http.get<SnapshotRecord[]>(`${this.monitorBaseUrl}/api/endpoints/${endpointId}/snapshots`);
  }

  getEndpointDiffs(endpointId: string): Observable<DiffRecord[]> {
    return this.http.get<DiffRecord[]>(`${this.monitorBaseUrl}/api/endpoints/${endpointId}/diffs`);
  }

  getRecentDiffs(limit = 40): Observable<DiffRecord[]> {
    return this.http.get<DiffRecord[]>(`${this.monitorBaseUrl}/api/diffs/recent`, {
      params: { limit },
    });
  }

  getSubscriptions(): Observable<SubscriptionRecord[]> {
    return this.http.get<SubscriptionRecord[]>(`${this.runtimeBaseUrl}/api/v1/subscriptions`);
  }

  getDlqEntries(): Observable<DlqEntry[]> {
    return this.http.get<DlqEntry[]>(`${this.runtimeBaseUrl}/api/v1/webhook-dlq`);
  }

  getDriftEventDlqEntries(): Observable<DriftEventDlqEntry[]> {
    return this.http.get<DriftEventDlqEntry[]>(`${this.runtimeBaseUrl}/api/v1/drift-event-dlq`);
  }

  replayDriftEventDlqEntry(dlqId: string): Observable<DriftEventReplayResult> {
    return this.http.post<DriftEventReplayResult>(`${this.runtimeBaseUrl}/api/v1/drift-event-dlq/${dlqId}/replay`, {});
  }

  getDeliveryAttempts(): Observable<DeliveryAttempt[]> {
    return this.http.get<DeliveryAttempt[]>(`${this.runtimeBaseUrl}/api/v1/webhook-delivery-attempts`);
  }

  getPayloadSnapshots(): Observable<DocumentArtifact[]> {
    return this.http.get<DocumentArtifact[]>(`${this.runtimeBaseUrl}/api/v1/documents/payload-snapshots`);
  }

  getSchemaDiffDocuments(): Observable<DocumentArtifact[]> {
    return this.http.get<DocumentArtifact[]>(`${this.runtimeBaseUrl}/api/v1/documents/schema-diffs`);
  }

  getValidationErrors(): Observable<DocumentArtifact[]> {
    return this.http.get<DocumentArtifact[]>(`${this.runtimeBaseUrl}/api/v1/documents/validation-errors`);
  }

  getReplayArtifacts(): Observable<DocumentArtifact[]> {
    return this.http.get<DocumentArtifact[]>(`${this.runtimeBaseUrl}/api/v1/documents/replay-artifacts`);
  }

  replayDlqEntry(dlqId: string): Observable<ReplayResult> {
    return this.http.post<ReplayResult>(`${this.runtimeBaseUrl}/api/v1/webhook-dlq/${dlqId}/replay`, {});
  }

  getRegistryOverview(): Observable<{ endpoints: EndpointRecord[]; subscriptions: SubscriptionRecord[] }> {
    return forkJoin({
      endpoints: this.getEndpoints(),
      subscriptions: this.getSubscriptions(),
    });
  }

  getEndpointDetail(endpointId: string): Observable<{
    endpoint: EndpointRecord;
    snapshots: SnapshotRecord[];
    diffs: DiffRecord[];
    subscriptions: SubscriptionRecord[];
  }> {
    return forkJoin({
      endpoint: this.getEndpoint(endpointId),
      snapshots: this.getEndpointSnapshots(endpointId),
      diffs: this.getEndpointDiffs(endpointId),
      subscriptions: this.getSubscriptions(),
    });
  }
}
