CREATE TYPE change_severity AS ENUM ('SAFE', 'RISKY', 'BREAKING');

CREATE TABLE api_endpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name VARCHAR(100) NOT NULL,
    http_method VARCHAR(10) NOT NULL,
    route_path VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(service_name, http_method, route_path)
);

CREATE TABLE schema_snapshots (
    fingerprint VARCHAR(64) PRIMARY KEY,
    endpoint_id UUID REFERENCES api_endpoints(id),
    normalized_schema JSONB NOT NULL,
    is_active_baseline BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE contract_drift_violations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_id UUID REFERENCES api_endpoints(id),
    observed_fingerprint VARCHAR(64) NOT NULL,
    severity change_severity NOT NULL,
    diff_payload JSONB NOT NULL,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
