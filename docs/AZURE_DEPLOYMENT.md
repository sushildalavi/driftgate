# Azure Deployment Notes (Azure-Compatible, Not Deployed)

DriftGate's event backend and document store are built to run against Azure services
without code changes, but **this repository has not been deployed to Azure**. Nothing
below should be read as "in production on Azure" — it describes the integration points
that exist in code today and what it would take to point them at real Azure resources.

## Cost-safety note

No Azure resources are required to run or test DriftGate. Local development and CI use
the no-op event backend and a local/Docker MongoDB instance. Only enable the Azure paths
below if you intentionally want to pay for and manage that infrastructure.

## Event backend: Azure Service Bus-compatible

`app/runtime/event_backends.py` defines `AzureServiceBusEventBackend`, selected via:

```bash
EVENT_BACKEND=azure_service_bus
```

`build_event_backend()` requires an explicit `service_bus_sender` when this mode is
selected; if one isn't supplied it raises a `RuntimeError` at startup instead of silently
falling back to no-op or crashing on first publish. This is the "safe config error"
behavior — see [`tests/test_event_backends.py`](../tests/test_event_backends.py).

To wire this up against a real Azure Service Bus namespace:

1. Create a Service Bus namespace and queue (default queue name: `drift-detected`,
   overridable via the `AzureServiceBusEventBackend.queue_name` field).
2. Install `azure-servicebus` and construct a `ServiceBusSender` from your connection
   string or managed identity.
3. Pass that sender into `build_event_backend(service_bus_sender=...)` during app
   startup instead of leaving it `None`.

No code changes are required beyond wiring the client — the backend already speaks
`ServiceBusMessage` when the SDK is importable and falls back to a raw JSON string
otherwise.

## Document store: Cosmos-compatible Mongo API

`app/runtime/document_store.py` stores payload snapshots, schema diffs, validation
errors, and replay artifacts through the MongoDB wire protocol. Azure Cosmos DB's API
for MongoDB implements the same protocol, so the same `pymongo`/`motor` client code can
point at a Cosmos connection string instead of local MongoDB:

```bash
MONGO_URI=mongodb://<cosmos-account>:<key>@<cosmos-account>.mongo.cosmos.azure.com:10255/?ssl=true&retrywrites=false
```

`retrywrites=false` is required by Cosmos DB's Mongo API and is the only
Cosmos-specific difference from local Docker MongoDB. No collection or index code
changes are needed. This has been reviewed for compatibility but **not run against a
live Cosmos account** — validate index behavior and RU consumption before relying on it
for anything beyond a portfolio demo.

## What "Azure-compatible" means here

- The code paths exist and are unit-tested against fakes/mocks.
- The abstractions (event backend protocol, document store protocol) do not assume a
  specific cloud vendor.
- Swapping in real Azure Service Bus or Cosmos DB is a configuration and client-wiring
  change, not a rewrite.

What it does **not** mean:

- No Azure subscription, resource group, or managed service has been provisioned for
  this project.
- No load or cost testing has been done against Azure Service Bus or Cosmos DB.
- There is no CI job that deploys to or validates against Azure.
