DO $$
BEGIN
    CREATE TYPE drift_event_dlq_status AS ENUM ('PENDING', 'REPLAYED');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE TABLE IF NOT EXISTS drift_event_dlq (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL UNIQUE,
    endpoint_id UUID NOT NULL REFERENCES contract_registry_endpoints(id) ON DELETE CASCADE,
    endpoint_name TEXT NOT NULL,
    namespace TEXT NOT NULL,
    payload JSONB NOT NULL,
    failure_reason TEXT NOT NULL,
    publisher_name TEXT NOT NULL,
    attempt_count INT NOT NULL DEFAULT 1,
    status drift_event_dlq_status NOT NULL DEFAULT 'PENDING',
    replay_error TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_failure_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    replayed_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS ix_drift_event_dlq_status_updated
ON drift_event_dlq(status, updated_at DESC);

CREATE INDEX IF NOT EXISTS ix_drift_event_dlq_endpoint_created
ON drift_event_dlq(endpoint_id, created_at DESC);
