export interface MonitorMetrics {
  endpoint_count: number;
  snapshot_count: number;
  severity_counts: Record<string, number>;
  drift_rate?: number;
  queue_lag?: number;
  dlq_count?: number;
  retry_count?: number;
  contract_review_count?: number;
  contract_review_insufficient_evidence_count?: number;
  drift_event_dlq_count?: number;
}

export interface EndpointRecord {
  id: string;
  name: string;
  provider: string;
  url: string;
  method: string;
  headers_json: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  latest_snapshot_hash?: string | null;
  latest_checked_at?: string | null;
}

export interface SnapshotRecord {
  id: string;
  endpoint_id: string;
  monitor_run_id: string;
  schema_hash: string;
  status_code: number;
  response_time_ms: number;
  response_size_bytes: number;
  normalized_schema_json?: unknown;
  raw_sample_json?: unknown;
  fetch_error?: string | null;
  created_at: string;
}

export interface DiffRecord {
  id: string;
  endpoint_id: string;
  old_snapshot_id?: string | null;
  new_snapshot_id: string;
  severity: string;
  change_type: string;
  path: string;
  old_type?: string | null;
  new_type?: string | null;
  old_value_json?: unknown;
  new_value_json?: unknown;
  message: string;
  created_at: string;
}

export interface SubscriptionRecord {
  id: string;
  consumer_id: string;
  endpoint_id: string;
  target_url: string;
  severity_threshold: string;
  schema_version?: number | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface DlqEntry {
  id: string;
  event_id: string;
  consumer_id: string;
  endpoint_id: string;
  target_url: string;
  payload: Record<string, unknown>;
  failure_reason: string;
  attempt_count: number;
  created_at: string;
  last_attempt_at: string;
}

export interface DriftEventDlqEntry {
  id: string;
  event_id: string;
  endpoint_id: string;
  endpoint_name: string;
  namespace: string;
  payload: Record<string, unknown>;
  failure_reason: string;
  publisher_name: string;
  attempt_count: number;
  status: 'PENDING' | 'REPLAYED';
  replay_error?: string | null;
  created_at: string;
  updated_at: string;
  last_failure_at: string;
  replayed_at?: string | null;
}

export interface DeliveryAttempt {
  id: string;
  event_id: string;
  consumer_id: string;
  endpoint_id: string;
  target_url: string;
  success: boolean;
  failure_reason?: string | null;
  attempt_count: number;
  attempted_at: string;
}

export interface DocumentArtifact {
  document_id: string;
  kind: string;
  created_at: string;
  source?: string;
  path?: string;
  payload?: unknown;
  errors?: unknown;
  classification?: string;
  endpoint_name?: string;
  diffs?: unknown;
  artifact_type?: string;
}

export interface ReplayResult {
  dlq_id: string;
  event_id: string;
  consumer_id: string;
  endpoint_id: string;
  target_url: string;
  replayed: boolean;
  failure_reason?: string | null;
  replayed_at: string;
}

export interface DriftEventReplayResult {
  replayed: boolean;
  error?: string | null;
  already_replayed?: boolean;
  dlq?: DriftEventDlqEntry | null;
}

export interface ContractReviewEvidenceItem {
  citation: string;
  kind: string;
  summary: string;
  details: Record<string, unknown>;
}

export interface ContractReviewOutcome {
  decision: 'approve' | 'needs_changes' | 'block';
  severity: 'compatible' | 'risky' | 'breaking';
  summary: string;
  consumer_impact: string;
  impacted_consumers?: string[];
  severity_explanation?: string;
  risk_summary?: string;
  rollout_action?: string;
  evidence: string[];
  recommended_fixes: string[];
  migration_note: string;
  review_comment: string;
  confidence: number;
  insufficient_evidence: boolean;
}

export interface ContractReviewContext {
  endpoint_id: string;
  endpoint_name: string;
  namespace: string;
  service_name: string;
  http_method: string;
  route_path: string;
  current_version?: number | null;
  schema_diffs: ContractReviewEvidenceItem[];
  payload_snapshots: ContractReviewEvidenceItem[];
  validation_failures: ContractReviewEvidenceItem[];
  dlq_entries: ContractReviewEvidenceItem[];
  delivery_attempts: ContractReviewEvidenceItem[];
  subscriptions: Record<string, unknown>[];
  drift_violations: ContractReviewEvidenceItem[];
  notes: string[];
  insufficient_evidence: boolean;
}

export interface ContractReviewRecord {
  review_id: string;
  endpoint_id: string;
  endpoint_name: string;
  provider: string;
  model_name?: string | null;
  created_at: string;
  latency_seconds: number;
  evidence_summary: string;
  consumer_impact: string;
  context: ContractReviewContext;
  review: ContractReviewOutcome;
}
