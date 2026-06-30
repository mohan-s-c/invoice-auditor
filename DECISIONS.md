# Decisions & Assumptions

Defaults chosen for an **offline-first, runnable** build of the Invoice Auditor. The handoff
(§0.4) says: where infra is unavailable, code against an interface + ship a mock behind a flag.
None of these introduce a paid dependency, and each keeps a clean seam for the real thing.

| # | Decision | Rationale | Swap path |
|---|----------|-----------|-----------|
| D1 | Python 3.12 · FastAPI · Pydantic v2 | per handoff §4 | — |
| D2 | **SQLite (stdlib)** for state / audit / labels instead of Postgres+Snowflake | zero-infra, offline | `libs/common/db.py` is the only persistence caller |
| D3 | **Offline deterministic "Qwen"** (`modelserve.OfflineProvider`) instead of a real local Qwen/vLLM | no GPU needed to run/demo; repeatable | `LLM_PROVIDER=oss` → `OpenAICompatProvider` (vLLM/Ollama, OpenAI-compatible); egress guard unchanged |
| D4 | **Egress guard is real** — any non-local model call hard-fails unless `ALLOW_EXTERNAL_MODEL=true` | handoff §10.3 (local-only AI) | — |
| D5 | **Deterministic detection** (rules + simple baselines) is the engine; the model adds the natural-language "why" + score | rules are exact + explainable (handoff §7) | add the Qwen scorer/classifier behind `detection` |
| D6 | **Served single-file UI** (the approved mockup, wired to the live API) instead of a React/Vite build | the design is already HTML; fastest faithful match, offline | port to React + Vite later; tokens/components are identical |
| D7 | No Temporal; in-process orchestration | single-node research build | — |
| D8 | Self-learning loop = **capture dispositions as labels** now; LoRA fine-tune/registry/promotion stubbed | Phase 2; capture is the prerequisite and is built | `services/learning` persists labels; `services/training` slots in |

## Guardrails honored (handoff §10)
- Humans own money decisions / high-value rejections — the agent **recommends**; disposition is a human action, audited.
- Local-only AI — egress guard blocks external model calls by default.
- Immutable audit with **model_version** on every flag/decision.
- RBAC region-scoping enforced server-side (HQ = all brands; Regional President = own brands).
- Auto-reject is **off** by default and gated by per-anomaly precision (settings/autonomy).

## Open items (from the handoff)
Which AP tool + API/webhook/payment-hold · GPU hosting for real Qwen + LoRA · pin Qwen releases ·
contract/rate-card + vendor-master feeds · category taxonomy conform · auto-reject $ threshold +
per-anomaly precision targets · notification channels + region→Regional-President map.
