# CatalogIQ — Production Deployment Guide

This guide provides the complete, authoritative, step-by-step instructions for deploying the **CatalogIQ** AI-powered Product Intelligence platform to production.

---

## 1. Architecture Overview

```
+-----------------------------------------------------------------------------------+
|                                  USER / BROWSER                                   |
+-----------------------------------------------------------------------------------+
                                          |
                      +-------------------+-------------------+
                      |                                       |
                      v                                       v
         +--------------------------+           +--------------------------+
         |     Frontend (Vercel)    |           |   Backend API (Render)   |
         |     React + Vite SPA     |           |     FastAPI Service      |
         |    (VITE_API_URL set)    |           |  (0.0.0.0:$PORT binding) |
         +--------------------------+           +--------------------------+
                                                              |
                   +------------------------------------------+--------------------+
                   |                                                               |
                   v                                                               v
      +-------------------------+                                            +--------------------+
      |  PostgreSQL (Managed)   |                                            |    Redis (Cache    |
      |   Catalog & Attributes  |                                            |  & Celery Broker)  |
      +-------------------------+                                            +--------------------+
                   ^                                                               |
                   |                         +-------------------------------------+
                   |                         v
                   |            +--------------------------+
                   |            |  Celery Worker (Render)  |
                   |            | Multi-stage Doc Parsing, |
                   |            | Extraction & Enrichment  |
                   +------------+--------------------------+
                                             |
                      +----------------------+----------------------+
                      |                      |                      |
                      v                      v                      v
        +-------------------------+ +------------------+ +-------------------------+
        |   Qdrant Cloud Cluster  | |  Google Gemini   | |   S3 / Object Store     |
        | Neural Vector Indexing  | |    Flash LLM     | |  Documents & Artifacts  |
        +-------------------------+ +------------------+ +-------------------------+
```

---

## 2. Infrastructure Services Provisioning

### A. Managed PostgreSQL Database (Render / Supabase / Neon)
1. In your cloud console (e.g., [Render Dashboard](https://dashboard.render.com/) -> **New** -> **PostgreSQL**):
   - **Name**: `catalogiq-db`
   - **Database**: `catalogiq`
   - **User**: `catalogiq_user`
   - **Region**: Choose region closest to your compute services (e.g., `Oregon (US West)` or `Frankfurt (EU)`).
2. Copy the **Internal Database URL** (for Render services in the same region) or **External Database URL**.
3. *Note*: Both `postgresql://` and `postgres://` prefixes are automatically recognized and normalized by CatalogIQ.

### B. Managed Redis Broker (Render / Upstash / Redis Cloud)
1. Create a Redis instance (e.g., Render Dashboard -> **New** -> **Redis**):
   - **Name**: `catalogiq-redis`
   - **Maxmemory Policy**: `noeviction` (recommended for Celery queues)
2. Copy the **Internal Redis URL** or **External Redis URL** (e.g., `rediss://...` or `redis://...`).

### C. Qdrant Cloud Vector Database
1. Sign up at [Qdrant Cloud Console](https://cloud.qdrant.io/).
2. Create a 1-node or multi-node cluster (e.g., `catalogiq-vectors`).
3. Generate an **API Key** under **Data Access Control / API Keys**.
4. Note your cluster endpoint URL (e.g., `https://xxxx-xxxx.us-east-1-0.aws.cloud.qdrant.io:6333`) and API Key.

### D. S3-Compatible Object Storage (AWS S3 / Cloudflare R2 / MinIO)
> [!IMPORTANT]
> Because Render Web Services and Background Workers run in separate containers with ephemeral local storage, production storage MUST use S3 or S3-compatible object storage so raw uploads and parsed JSON files are accessible across all workers and API nodes.

1. Create a bucket (e.g., `catalogiq-production-storage`).
2. Generate IAM Access Key and Secret Key with `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject` permissions.
3. If using Cloudflare R2:
   - Endpoint URL: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`
   - Region: `auto` or `us-east-1`

### E. Google Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com/).
2. Create an API Key.
3. Recommended model: `gemini-2.5-flash` or `gemini-3.5-flash`.

---

## 3. Backend Deployment (Render Web Service)

1. Connect your repository to Render -> **New Web Service**.
2. Configure settings:
   - **Name**: `catalogiq-api`
   - **Root Directory**: `backend`
   - **Environment**: `Python 3`
   - **Build Command**:
     ```bash
     pip install -r requirements.txt && alembic upgrade head
     ```
   - **Start Command**:
     ```bash
     uvicorn app.main:app --host 0.0.0.0 --port $PORT
     ```
3. Set **Environment Variables**:

| Variable | Recommended Value / Description |
| :--- | :--- |
| `ENV` | `production` |
| `APP_NAME` | `CatalogIQ` |
| `DATABASE_URL` | `postgresql://catalogiq_user:...@dpg-xxx.render.com/catalogiq` |
| `REDIS_URL` | `redis://...` or `rediss://...` |
| `QDRANT_URL` | `https://xxxx.cloud.qdrant.io:6333` |
| `QDRANT_API_KEY` | `your_qdrant_api_key` |
| `QDRANT_COLLECTION_NAME` | `catalogiq_products` |
| `STORAGE_PROVIDER` | `s3` |
| `AWS_ACCESS_KEY_ID` | `your_s3_access_key` |
| `AWS_SECRET_ACCESS_KEY` | `your_s3_secret_key` |
| `S3_BUCKET_NAME` | `catalogiq-production-storage` |
| `S3_ENDPOINT_URL` | `https://s3.us-east-1.amazonaws.com` |
| `S3_REGION` | `us-east-1` |
| `LLM_PROVIDER` | `gemini` |
| `GEMINI_API_KEY` | `your_google_gemini_api_key` |
| `GEMINI_MODEL` | `gemini-2.5-flash` |
| `CORS_ORIGINS` | `https://your-frontend.vercel.app,http://localhost:5173` |
| `EMBEDDING_PROVIDER` | `fastembed` |
| `EMBEDDING_MODEL` | `text-embedding-3-small` |
| `WORKER_CONCURRENCY` | `4` |

---

## 4. Background Worker Deployment (Render Celery Worker)

1. In Render Dashboard -> **New** -> **Background Worker**.
2. Configure settings:
   - **Name**: `catalogiq-worker`
   - **Root Directory**: `backend`
   - **Environment**: `Python 3`
   - **Build Command**:
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command**:
     ```bash
     celery -A app.workers.celery_app.celery_app worker --loglevel=info --concurrency=4
     ```
3. Set the **same environment variables** as the Backend Web Service (`DATABASE_URL`, `REDIS_URL`, `QDRANT_URL`, `QDRANT_API_KEY`, `STORAGE_PROVIDER`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME`, `GEMINI_API_KEY`, `GEMINI_MODEL`).

---

## 5. Frontend Deployment (Vercel)

1. Connect your repository to [Vercel](https://vercel.com/) -> **New Project**.
2. Configure project settings:
   - **Framework Preset**: `Vite`
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
3. Add **Environment Variables**:

| Variable | Value |
| :--- | :--- |
| `VITE_API_URL` | `https://catalogiq-api.onrender.com` (Your deployed Render backend URL) |

4. Client-side routing is handled automatically by the included [`vercel.json`](file:///c:/Projects/UniLog_CatalogIQ/frontend/vercel.json) rewrites.

---

## 6. Database Migrations

CatalogIQ manages schema migrations through Alembic.
The build step on Render executes:
```bash
alembic upgrade head
```
To run migrations manually from local machine against production:
```bash
DATABASE_URL="postgresql://user:pass@host/db" alembic upgrade head
```

---

## 7. Post-Deployment Smoke Test Checklist

Once all services are deployed:

1. **Liveness & Readiness Healthcheck**:
   - `GET https://your-backend.onrender.com/api/v1/health/live` -> `{"status":"ok"}`
   - `GET https://your-backend.onrender.com/api/v1/health/ready` -> `{"status":"healthy","services":{"postgresql":"healthy","redis":"healthy","qdrant":"healthy"}}`
2. **Catalog Health Overview**:
   - `GET https://your-backend.onrender.com/api/v1/health/catalog` -> Returns catalog KPIs.
3. **Frontend Application**:
   - Navigate to `https://your-frontend.vercel.app/`
   - Verify Landing Page, Catalog Dashboard, Upload Console, Search, and Reviews shells render cleanly without CORS errors.
4. **Document Ingestion Test**:
   - Upload a test datasheet/CSV via `/upload`.
   - Verify the Celery worker parses the file, extracts attributes with Gemini, and upserts embeddings to Qdrant Cloud.
5. **AI Assistant Test**:
   - Open the CatalogIQ Assistant widget in the bottom right.
   - Ask a question and verify low-latency Gemini responses.
