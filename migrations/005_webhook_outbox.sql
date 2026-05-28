DO $$ BEGIN
    CREATE TYPE webhook_outbox_status AS ENUM ('PENDING', 'DELIVERING', 'FAILED', 'DELIVERED');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS webhook_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id UUID NOT NULL REFERENCES consumer_subscriptions(id) ON DELETE CASCADE,
    endpoint_id UUID NOT NULL REFERENCES contract_registry_endpoints(id) ON DELETE CASCADE,
    payload JSONB NOT NULL,
    status webhook_outbox_status NOT NULL DEFAULT 'PENDING',
    attempts INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    next_retry_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_webhook_outbox_pending_next_retry
ON webhook_outbox(status, next_retry_at);

CREATE INDEX IF NOT EXISTS ix_webhook_outbox_subscription
ON webhook_outbox(subscription_id);
