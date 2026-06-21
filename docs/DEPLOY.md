# ActiveEnv — Deployment Runbook

Backend + Postgres + Redis + Celery run on **Alibaba Cloud ECS** via Docker
Compose. The frontend deploys to **Vercel** (or the same ECS box as a fallback).

This is a step-by-step you can follow start to finish. Anything that needs the
Alibaba console is called out as **[console]**.

---

## 0. Prerequisites

- An Alibaba Cloud account (activated, billing enabled).
- A DashScope / Model Studio API key (for real intent inference — optional;
  without it the system still classifies deterministically in simulation mode).
- The repo pushed to GitHub.

---

## 1. Provision the ECS instance **[console]**

1. **ECS → Instances → Create Instance.**
2. Spec: **2 vCPU / 4 GB** (`ecs.e-c1m2.large` or similar) is plenty.
3. Image: **Ubuntu 22.04 64-bit.**
4. Storage: 40 GB ESSD (Docker images + Postgres volume).
5. Public IP: **assign one** (pay-as-you-go bandwidth is fine for a demo).
6. Region: **Singapore** (matches the default Model Studio intl endpoint).

### Security group (inbound rules) **[console]**

| Port | Source | Purpose |
|------|--------|---------|
| 22   | your IP only | SSH |
| 80, 443 | 0.0.0.0/0 | HTTP/HTTPS (if you add a reverse proxy / TLS) |
| 8000 | 0.0.0.0/0 | API (lock to the frontend egress IP if you can) |

> Postgres (5432) and Redis (6379) are **not** exposed — they only talk to the
> app over the internal Docker network.

---

## 2. Install Docker on the box

SSH in (`ssh root@YOUR_ECS_IP`), then:

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
docker --version && docker compose version
```

---

## 3. Get the code + configure

```bash
git clone https://github.com/mishrasuman7/ActiveEnv.git
cd ActiveEnv
cp .env.production.example .env
nano .env        # fill in the values below
```

Fill in `.env`:

- `DJANGO_SECRET_KEY` — `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`
- `DJANGO_DEBUG=false`
- `DJANGO_ALLOWED_HOSTS=YOUR_ECS_IP` (add a domain later if you have one)
- `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` — your Vercel URL
- `POSTGRES_PASSWORD` — a strong value
- `ACTIVEENV_ENCRYPTION_KEY` — `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `DASHSCOPE_API_KEY` — your Model Studio key (or leave blank)
- `SIMULATE_PROBES=true` for the safe demo; `false` to probe the submitted
  targets for real.

---

## 4. Launch the stack

```bash
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

This builds the backend image, runs migrations (one-shot `migrate` service),
then starts `web` (gunicorn), `worker` (celery), `postgres`, and `redis`.

Verify:

```bash
docker compose -f docker-compose.prod.yml ps          # all healthy
curl -s http://localhost:8000/api/health/             # {"status":"ok",...}
curl -s http://YOUR_ECS_IP:8000/api/health/           # reachable publicly
```

Create an admin user (optional, for the Django admin):

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

---

## 5. Deploy the frontend (Vercel)

1. Import the GitHub repo at vercel.com → **root directory `frontend/`**.
2. Set env var **`NEXT_PUBLIC_API_BASE_URL = http://YOUR_ECS_IP:8000`**.
3. Deploy. Vercel auto-detects Next.js; `output: "standalone"` is ignored there.
4. Copy the deployed URL back into the ECS `.env`
   (`CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`) and
   `docker compose ... up -d` again to apply.

> **Mixed-content note:** a Vercel (HTTPS) page calling an `http://` API will be
> blocked by the browser. For a clean demo either (a) put the API behind HTTPS
> (domain + free TLS via a reverse proxy / Alibaba SLB), or (b) demo the
> frontend from `http://YOUR_ECS_IP:3000` using the fallback container below.

### Fallback: frontend on the same ECS box

```bash
docker build -t activeenv-frontend \
  --build-arg NEXT_PUBLIC_API_BASE_URL=http://YOUR_ECS_IP:8000 ./frontend
docker run -d --name activeenv-frontend -p 3000:3000 activeenv-frontend
```

(Open port 3000 in the security group first.)

---

## 6. Updating

```bash
git pull
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

Migrations re-run automatically via the `migrate` service.

---

## 7. Operations cheatsheet

```bash
# logs
docker compose -f docker-compose.prod.yml logs -f web
docker compose -f docker-compose.prod.yml logs -f worker

# restart just the API
docker compose -f docker-compose.prod.yml restart web

# DB backup
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U activeenv activeenv > backup_$(date +%F).sql

# tear down (keeps volumes)
docker compose -f docker-compose.prod.yml down
```

---

## 8. Go-live checklist

- [ ] `/api/health/` returns `ok` from the public IP
- [ ] `DJANGO_DEBUG=false`, real `DJANGO_SECRET_KEY`, real `ACTIVEENV_ENCRYPTION_KEY`
- [ ] Frontend loads and a run completes end to end (example → 2 silently_wrong)
- [ ] Approve → green-loop works against the deployed API
- [ ] Postgres/Redis ports NOT publicly reachable
- [ ] (If real probes) `SIMULATE_PROBES=false` and Qwen key set
