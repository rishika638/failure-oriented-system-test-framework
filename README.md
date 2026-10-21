# Production Failure Capture & Replay Engine

Capture redacted, measured failures from an instrumented service; group them into incidents; replay approved GET scenarios against an isolated synthetic target; and compare failure reproduction with a clean recovery run. Replays are asynchronous and never target the captured production host.

## Architecture and workflow

```text
Express SDK -> authenticated capture API -> redacted, checksummed snapshot
            -> PostgreSQL incident/audit history -> Redis/RQ replay job
            -> bounded worker -> allowlisted fault proxy -> synthetic target
            -> injected/recovery artifacts -> comparison -> dashboard history
```

The SDK observes completed requests but emits only scenarios selected by the application. The API validates, normalizes, fingerprints, and persists each snapshot with its incident. Replay submission requires an organization-scoped API key, a capture belonging to that incident, and an idempotency key. The worker verifies snapshot integrity and a versioned fixture before running a bounded GET fault followed by a separate clean recovery request. Original measurements, replay measurements, comparison results, and lifecycle audit events remain distinct and visible in incident history.

## Product boundaries

- The capture SDK sends only explicitly selected GET requests. Captures are asynchronous and best-effort; a capture outage does not block the application.
- Payloads are size-bounded and secrets in headers/body are redacted before transmission and again before persistence. Raw response bodies, credentials, and production URLs are not stored.
- Replay paths and methods come from versioned fixtures, not captured URLs or user-provided requests. `REPLAY_TARGET_URL` must be configured and its exact hostname listed in `REPLAY_ALLOWED_HOSTS`. Redirects are not followed; private/reserved targets are denied except in explicit local development mode.
- Replay and proxy upstream hostnames are resolved and checked against public/private address rules. Private hosted services must be named explicitly in their private-host allowlists. Only operator-controlled synthetic service URLs belong in these settings.
- Replay only supports fixture-defined GETs through an approved synthetic HTTP proxy. The proxy accepts only `/ping` and `/dependency`, a shared internal token, and a fixed allowlisted upstream; it never forwards credentials or follows redirects. Application delay, jitter, timeout, connection abort, and dependency failures are supported. A proxy/application abort is not physical packet loss.
- Linux `tc/netem` remains an optional local experiment. It refuses to overwrite an existing root qdisc, tracks its own delay, and only removes the configuration it installed. The experiment reports whether configured delay measurably changed p95; interface selection alone does not prove that the traffic passed through it.
- No production request is automatically replayed. No arbitrary URL fetches, shell commands, privileged containers, or external side-effecting methods are supported.

## Local startup (Windows PowerShell)

Prerequisites: Docker Desktop with Compose, Node.js 20.19+ (22.13+ recommended), and Python 3.11+.

```powershell
Copy-Item .env.example .env
docker compose -f docker-compose.test.yml up --build
```

The API is at `http://localhost:8000`; liveness is `GET /health`, and readiness is `GET /ready`. PostgreSQL migrations run before the API starts. Redis and the replay proxy are internal Compose services; the synthetic target is bound to loopback at `127.0.0.1:8080` for local baseline tests. Open `apps/dashboard` in another terminal to run the UI:

```powershell
Set-Location apps/dashboard
npm ci
$env:VITE_API_BASE_URL = "http://localhost:8000"
npm run dev
```

Open `http://localhost:5173` and use `local-dev-key` from the development `.env.example`. This key is intentionally development-only. For an end-to-end smoke test, use the API capture endpoint:

```powershell
$capture = @{
  scenario = "latency"; method = "GET"; path = "/ping"; status_code = 200
  latency_ms = 360; request_id = [guid]::NewGuid().ToString()
  headers = @{ "user-agent" = "synthetic-smoke-test" }
  occurred_at = [DateTime]::UtcNow.ToString("o")
} | ConvertTo-Json
$created = Invoke-RestMethod http://localhost:8000/v1/captures `
  -Method Post -Headers @{ Authorization = "Bearer local-dev-key" } `
  -ContentType "application/json" -Body $capture
$created
```

For the complete SDK path, build [sdk/node](./sdk/node), install the package in an Express service, and instrument its request handler using the example below. Make an approved synthetic GET whose scenario predicate selects it; the capture appears in the API/dashboard without blocking the request. Use the returned incident and capture in the dashboard and choose **Run replay**. The worker injects the fixture's 300 ms delay into the synthetic target, then issues a separate clean recovery request. Both artifacts, the evidence-based comparison, and audit history appear in incident detail.

Stop the local stack with `Ctrl+C` or `docker compose -f docker-compose.test.yml down`. To remove local database data, explicitly remove the named Compose volume with `docker compose -f docker-compose.test.yml down --volumes`.

To apply or inspect migrations manually in the running API container, run `docker compose exec api alembic upgrade head` or `docker compose exec api alembic current`. Local development without Compose defaults to `DATABASE_URL=sqlite:///./failure_engine.db`; that file is ignored by Git.

## Development checks

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest

Set-Location apps/dashboard
npm ci
npm run lint
npm run build

Set-Location ..\..\sdk\node
npm ci
npm test
```

`python -m pytest` includes unit, API/security integration, replay recovery, real HTTP abort, worker failure callback, tenant isolation, SSRF boundaries, idempotent submission, netem cleanup, and SDK outage tests. `npm run build` includes dashboard TypeScript checking. `npm test` builds the SDK and verifies redaction and asynchronous best-effort capture behavior. Python type diagnostics were checked with Pylance and Python lint uses Ruff. GitHub Actions runs the Python, dashboard, and SDK checks.

SQLite migration check:

```powershell
$env:DATABASE_URL = "sqlite:///./migration-check.db"
python -m alembic upgrade head
python -m alembic check
```

Remove the generated migration-check database after use; SQLite is not a hosted persistence substitute.

## API and configuration

The API is FastAPI + Pydantic 2; SQLAlchemy 2 persists tenant-scoped incidents, captures, replay jobs, comparisons, and audit events. Alembic owns schema changes. Each request needs an organization-scoped bearer key. `API_KEYS_JSON` maps organization IDs to API keys, for example `{"acme":"replace-with-a-long-random-key"}`. In production, provide this from the platform's secret store and set `APP_ENV=production`; there is no production fallback key.

Required API/worker environment:

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | Must be `development` or `production`; production disables development defaults and local/private target exceptions. |
| `API_KEYS_JSON` | JSON object mapping organization IDs to bearer keys. |
| `DATABASE_URL` | PostgreSQL SQLAlchemy URL, e.g. `postgresql+psycopg://user:password@host:5432/db`. |
| `REDIS_URL` | Redis-compatible URL used by the bounded single-process RQ worker. |
| `CORS_ORIGINS` | Comma-separated exact dashboard origins; production requires explicit HTTPS origins and rejects `*`. |
| `REPLAY_TARGET_URL` | Base URL for the approved synthetic fault proxy; never a captured request URL. |
| `REPLAY_ALLOWED_HOSTS` | Comma-separated exact hostnames allowed for replay. |
| `REPLAY_ALLOWED_PRIVATE_HOSTS` | Exact operator-managed private service hostnames allowed for private synthetic deployments; empty by default. |
| `REPLAY_ALLOW_PRIVATE_TARGETS` | Must remain unset/false in production. Compose sets it only for local development. |
| `FAULT_UPSTREAM_URL` | Fixed base URL for the synthetic proxy's upstream service. |
| `FAULT_ALLOWED_HOSTS` | Exact allowlist for the proxy's configured synthetic upstream. |
| `FAULT_ALLOWED_PRIVATE_HOSTS` | Exact managed synthetic upstream hostnames allowed to resolve to private addresses. |
| `FAULT_PROXY_TOKEN` | Long random token shared by the worker and synthetic proxy. |
| `WORKER_MAX_JOBS` | Worker process exit/recycle limit (1–10,000); RQ executes one job at a time per worker process. |
| `CAPTURE_BODY_ENABLED` | Defaults to false. Set true only when the organization explicitly enables redacted request-body capture. |

Migrations: `alembic upgrade head`. API start: `alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port $PORT`. Worker start: `python -m worker.main`. API `GET /health` is liveness; `GET /ready` checks required configuration, PostgreSQL, Redis, the synthetic proxy, and (in production) an active RQ worker. Set a platform execution timeout above 60 seconds for API requests; each replay job has a 60-second RQ timeout. Add worker replicas only to increase bounded, single-job-at-a-time concurrency.

## Hosted deployment

### Vercel dashboard

Create a Vercel project rooted at `apps/dashboard`, select Node.js 22.x, and use **Install Command** `npm ci`, **Build Command** `npm run build`, and **Output Directory** `dist`. Set `VITE_API_BASE_URL` to the public Render API origin; it is public configuration, not a secret. Set the API's `CORS_ORIGINS` to the exact Vercel deployment/custom-domain origins. Deploy the dashboard over HTTPS. Organization API keys are entered by the operator and held in `sessionStorage`, never embedded in the build.

### Render API and worker

Create a Render **Web Service** from this repository with **Dockerfile Path** `Dockerfile.api`. Set `APP_ENV=production`, `PORT=8000` (or use Render's injected `PORT`), `API_KEYS_JSON`, `CORS_ORIGINS`, `DATABASE_URL`, `REDIS_URL`, `REPLAY_TARGET_URL`, `REPLAY_ALLOWED_HOSTS`, `REPLAY_ALLOWED_PRIVATE_HOSTS`, and `FAULT_PROXY_TOKEN` as service environment/secrets. The container runs `alembic upgrade head` before Uvicorn. Configure health check path `/ready`.

Create a Render **Background Worker** from the same repository with **Dockerfile Path** `Dockerfile.worker`; use the start command `python -m worker.main`. Set `APP_ENV=production`, `DATABASE_URL`, `REDIS_URL`, `REPLAY_TARGET_URL`, `REPLAY_ALLOWED_HOSTS`, `FAULT_PROXY_TOKEN`, and optionally `WORKER_MAX_JOBS`. Use a SQLAlchemy-compatible URL with the `postgresql+psycopg://` scheme; the application also normalizes Render-style `postgres://` and `postgresql://` URLs to the installed psycopg 3 driver. Provision managed PostgreSQL and a Redis-compatible managed service, then use their private/internal URLs. The production replay target must be a separately hosted, synthetic service under an operator-controlled hostname; add only that exact hostname to `REPLAY_ALLOWED_HOSTS`. Do not set `REPLAY_ALLOW_PRIVATE_TARGETS=true`. Local Compose is separate and does not require privileged containers or nested Docker.

For hosted synthetic replays, create a Render **Private Service** for the demo target with `Dockerfile.target` and a second Private Service with `Dockerfile.proxy`. Set `FAULT_UPSTREAM_URL` to the target's internal HTTP URL and include its exact hostname in both `FAULT_ALLOWED_HOSTS` and `FAULT_ALLOWED_PRIVATE_HOSTS`. On the API and worker, point `REPLAY_TARGET_URL` at the proxy's internal URL and list only its exact hostname in `REPLAY_ALLOWED_HOSTS` and `REPLAY_ALLOWED_PRIVATE_HOSTS`. Set the same strong random `FAULT_PROXY_TOKEN` on the proxy and worker; never reuse the local example value. HTTP is accepted only for these exact explicitly allowlisted private service hostnames. The private target/proxy are synthetic-only and must not forward to production or arbitrary third-party services.

## Capturing from Express

Build the SDK with `cd sdk/node; npm ci; npm run build`, then use the built package from your Express app:

```ts
import express from "express";
import { captureMiddleware } from "@failure-engine/express-sdk";

const app = express();
app.use(express.json({ limit: "16kb" }));
app.use(captureMiddleware({
  apiUrl: process.env.FAILURE_ENGINE_API_URL!,
  apiKey: process.env.FAILURE_ENGINE_API_KEY!,
  scenarioForRequest: (_request, statusCode, latencyMs) =>
    statusCode >= 500 ? "dependency" : latencyMs > 250 ? "latency" : undefined,
  // Request bodies are excluded unless deliberately enabled and allowed by the API.
  onCaptureError: (error) => console.warn("Failure capture unavailable", error),
}));
```

Keep API keys in server-side secret storage. Use a scenario predicate that reflects measured failures in your service. Request bodies are off by default; opt in with `captureBody: true` and `CAPTURE_BODY_ENABLED=true` only when necessary. Captures are redacted, do not include credentials/cookies, never block the response, and never trigger replay.

## Experiments and evidence

Baseline traffic: `python -m traffic.run_baseline --url http://127.0.0.1:8080/ping --rps 10 --duration 20 --timeout 1`. Control RPS, duration, timeout, and concurrency. Metrics include scheduled/completed requests, status counts, timeouts, other errors, missed slots, throughput, error rate, and interpolated p50/p95/p99.

Optional Linux netem experiment (requires `tc`, appropriate privileges, and an explicitly chosen `NETEM_INTERFACE` or `--interface`):

```powershell
python experiments/run_latency.py --url http://<controlled-target>/ping --interface eth0 --netem-delay-ms 300
```

Never assume the injected interface affects the tested route. The script cleans up in `finally` and reports `fault_effect_confirmed` only when the measured p95 delta reaches half the configured delay; false means this experiment did not demonstrate effect. Do not run the netem experiment against production.

## Known limitations

- Replay supports only checked-in `latency`, `timeout`, and `dependency` GET fixtures and their fixed paths. Arbitrary methods, URLs, request bodies, production replay, and external side effects are intentionally unsupported.
- Each RQ worker processes one job at a time; add worker instances to raise aggregate concurrency. Redis/RQ and PostgreSQL do not share a distributed transaction; an enqueue outage is recorded as a failed replay and surfaced to the caller.
- Dashboard credentials are organization API keys supplied by an operator and held in browser `sessionStorage`; there is no user/SSO account system or API-key management UI.
- Hosted deployment, managed PostgreSQL/Redis provisioning, DNS, and custom domain configuration are operator tasks. No deployment or benchmark is implied by this repository.
- `tc/netem` is optional, Linux-only, and requires host networking privileges when deliberately run locally. It is not included in hosted worker images or hosted replay.
