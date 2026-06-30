# Deploying Invoice Auditor

The app is a stateful **FastAPI + SQLite** service that serves a single-page UI and an
`/api/*` surface. Netlify cannot run the Python server itself (it hosts static files +
short-lived functions only), so the deployment is split:

- **Render** runs the backend (the long-lived FastAPI web service).
- **Netlify** serves the UI shell and **proxies** `/api/*` to the Render backend.

The frontend calls the API with relative paths (`/api/...`) and has **no offline fallback**,
so a live backend is required for the UI to render anything.

---

## 1. Backend on Render (`render.yaml`)

1. Render dashboard → **New → Blueprint** → select the `mohan-s-c/invoice-auditor` repo.
2. Render reads `render.yaml`:
   - build: `pip install -e .`
   - start: `uvicorn services.dashboard_api.app:app --host 0.0.0.0 --port $PORT`
   - health check: `/api/health`
3. Deploy. The SQLite DB **self-seeds on first boot** (`lifespan → seed_all`), so the demo
   data appears with no extra steps.
4. Note the service URL, e.g. `https://invoice-auditor-api.onrender.com`.

**Guardrail:** `LLM_PROVIDER=offline` and `ALLOW_EXTERNAL_MODEL=false` are set so the hosted
demo keeps all AI local/offline — no external model egress.

**Persistence:** the free plan's disk is ephemeral, so dispositions/fine-tune state reset on
redeploy (fine for a demo). For durable state, attach a Render **Disk** mounted at `/data` and
set `DB_PATH=/data/invoice_auditor.db`.

> Render free web services also sleep after inactivity; the first request after idle takes a
> few seconds to wake.

## 2. Frontend on Netlify (`netlify.toml`)

1. Edit `netlify.toml` → replace the proxy host with your Render URL from step 1.4:
   ```toml
   to = "https://<your-render-service>.onrender.com/api/:splat"
   ```
   Commit and push.
2. Netlify → **Add new site → Import an existing project** → pick the repo.
   - publish directory: `services/dashboard_api/static`
   - build command: *(none)*
3. Deploy. Netlify serves `index.html` and rewrites `/api/*` to Render (same-origin proxy →
   no CORS needed).

## Alternative: everything on Render (no Netlify)

If you don't need Netlify, the Render service from step 1 already serves the UI at `/`
(FastAPI mounts the static dir and returns `index.html`). Just open the Render URL directly.
