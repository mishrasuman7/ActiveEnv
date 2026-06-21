# ActiveEnv

**The agent that catches the config value that is present, valid, authenticating — and still silently wrong.**

ActiveEnv is an Autopilot agent built for the **Alibaba Cloud / Qwen Global AI Hackathon (Track 4 — Autopilot Agent)**. It infers what each config value is *supposed* to be by reading how it is used in your codebase, then **actively probes the real system** (read-only) to see what it *actually* does — flagging mismatches with evidence, and (after human approval) applying a fix and re-probing until reality matches intent.

It is **not** a `.env` linter. A linter checks format and presence. ActiveEnv checks **truth**.

---

## The closed loop

```
infer intent → probe reality → classify → [human approves] → apply fix → re-probe → green
```

## v1 probe adapters (each provably reliable, all read-only)

| Adapter | Catches | How |
|---|---|---|
| **Postgres** | staging DB used in prod | `SELECT current_database(), inet_server_addr(), version()` |
| **Stripe** | test key in prod (or live in test) | `sk_test_`/`sk_live_` + API `livemode` flag |
| **GitHub** | wrong account / org / scope | `GET /user`, `/repos` identity & scope |

## Tech stack

- **Frontend:** Next.js (React) + Tailwind — the live demo surface
- **Backend:** Django REST Framework + Celery + Redis
- **LLM:** Qwen via Alibaba Cloud Model Studio (OpenAI-compatible, function calling)
- **Agent ↔ tools:** custom `config-probe-mcp` MCP server (3 read-only probe tools)
- **Datastore:** Postgres (runs, findings, audit log)
- **Deploy:** Alibaba Cloud ECS (Singapore) + Docker; frontend on Vercel

## Repository layout

```
backend/    Django REST + Celery orchestrator, Qwen agent loop, API
frontend/   Next.js demo surface
mcp/        config-probe-mcp server (3 read-only probe tools)
docs/       build roadmap, architecture diagram
scripts/    dev helpers
```

## Quick start (local dev)

```bash
# 1. Copy env template and fill in DASHSCOPE_API_KEY
cp .env.example .env

# 2. Start Postgres + Redis
docker compose up -d

# 3. Backend
cd backend && python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements.txt
python manage.py migrate && python manage.py runserver

# 4. Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

## Safety model (non-negotiable)

- Probes are **strictly read-only** — connect / authenticate / GET only. Never write.
- Secrets masked everywhere (UI, logs, audit). Never stored in plaintext or in URL params.
- Fixes require **explicit human approval** before being applied; re-probe after to confirm.
- Full audit trail with undo on every action.

## Hackathon compliance (Stage 1)

- [ ] Built with Qwen models on Model Studio
- [ ] Backend deployed on Alibaba Cloud + code file proving Alibaba Cloud API use (`backend/alibaba_proof.py`)
- [ ] Public repo + OSS license (MIT — see `LICENSE`)
- [ ] Architecture diagram + text description
- [ ] Demo video < 3 min, public, English
- [ ] Track: Autopilot Agent

## License

[MIT](LICENSE) © 2026 Suman Mishra
