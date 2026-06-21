# ActiveEnv — Security & Compliance

ActiveEnv inspects configuration that, by definition, contains secrets. Its
whole job runs on trust, so safety is a design constraint, not an afterthought.
This document is the compliance reference for how that trust is honored.

---

## 1. Threat model

ActiveEnv is given (a) a config file/blob and (b) optionally the codebase that
uses it. It must determine whether each value is *correct for its environment*
without ever (i) leaking a secret, (ii) mutating a target system, or
(iii) inventing a problem that isn't there.

The three corresponding guarantees:

| Risk | Guarantee | Where enforced |
|------|-----------|----------------|
| Secret leakage | Values are masked in every response and encrypted at rest | `masking.py`, `crypto.py` |
| Side effects on targets | Probes are strictly **read-only** | `probes/*`, `prober.py` |
| Fabricated findings | Deterministic classifier + AI hallucination guard | `classify.py`, `intent.py` |

---

## 2. Secret handling

- **Masking.** Secret values never appear in API output. `mask_value` keeps a
  short, non-reversible hint (e.g. `sk_test_********6789`) — enough for a human
  to recognize the key, useless to an attacker.
- **Encryption at rest.** A probeable secret must be re-readable to re-probe
  after a fix, so it is stored as `ConfigKey.secret_ciphertext`, encrypted with
  **Fernet (AES-128-CBC + HMAC)**. Plaintext is never persisted.
- **Key management.** The vault key comes from `ACTIVEENV_ENCRYPTION_KEY`
  (a dedicated Fernet key) in production. In dev it is derived from
  `DJANGO_SECRET_KEY` for convenience. Rotating the key re-encrypts on next
  write.
- **No secret in logs.** Probe evidence and audit entries record masked inputs
  and observed *facts about* the target, never the raw credential.

## 3. Read-only probes

Every probe is a read-only identity/metadata check — it answers "what is this
credential actually pointed at?" and nothing else:

- **Database** — connects and reads `current_database()`, host, server version.
  No writes, no schema access.
- **Stripe** — reads key mode (`livemode`) from the key itself / a metadata
  call. No charges, no object creation.
- **GitHub** — reads the token's own identity and scopes. No repo mutation.

There is no code path that writes to a target system. A **simulation mode**
(`SIMULATE_PROBES=true`) derives the same evidence from self-describing parts of
a value (a `sk_test_` prefix *is* test mode; a URL host *is* the connect host),
so the product can be demonstrated with zero external credentials and zero
network calls to third parties.

## 4. Human-in-the-loop for any change

ActiveEnv never changes a value on its own.

- A fix is only applied through `POST /api/findings/<id>/approve/`, which
  **requires** an explicit `corrected_value` — the approval gate. No corrected
  value, no change (HTTP 400).
- Every apply/re-probe/undo is written to an **audit log** surfaced in the run
  detail.
- Every fix snapshots the previous state and is **reversible** via
  `POST /api/findings/<id>/undo/`.

## 5. Grounding the AI (no fabrication)

Intent inference uses an LLM (Qwen); classification does not. The AI proposes
*intent*, the deterministic classifier decides *findings*:

- The Qwen system prompt enforces strict grounding: no fabrication, no
  extrapolation beyond the provided code and config.
- A **hallucination guard** drops any AI-returned finding whose `finding_id`
  is not present in the scanner's own output — the model cannot introduce
  findings the deterministic layer didn't already produce.
- Inconclusive checks (e.g. DKIM) are reported as `INFO`/"inconclusive" rather
  than asserted, and the model is instructed not to generalize from them.

## 6. Data retention

- Inputs (config + code) are processed to produce findings and the encrypted
  vault entry; they are not shared with any third party beyond the optional
  Qwen call used for intent inference.
- A run and its data can be deleted with the run record; there is no external
  copy.

## 7. Deployment posture

- Postgres and Redis are never exposed publicly — they are reachable only on the
  internal Docker network (see `docker-compose.prod.yml`).
- Production runs with `DJANGO_DEBUG=false`, a unique `DJANGO_SECRET_KEY`, and a
  dedicated vault key.
- The API container runs as a non-root user.
- TLS/secure-cookie settings activate automatically when `DEBUG=false`; see
  `.env.production.example`.

---

*Scope: this is a hackathon/demo project. The guarantees above are implemented
and tested (30 backend tests), but a production rollout against real customer
secrets would additionally want a managed KMS for the vault key, per-tenant
isolation, and audit-log retention policy.*
