# DriftGate Angular Dashboard

This dashboard renders the DriftGate registry, drift review, webhook reliability, DLQ replay, and document-store views.

## Local development

```bash
npm install
npm start
```

The app is served on `http://localhost:4200` in development and `http://localhost:5173` when served through Docker Compose.

## Validation

```bash
npm run build
npm test -- --watch=false --browsers=ChromeHeadless
```

## Deployment

The production image is built from `frontend/Dockerfile` and served through Nginx.
