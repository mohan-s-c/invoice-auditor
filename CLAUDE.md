# Invoice Auditor (AI App + Agent)

Implement per `../INVOICE_AUDITOR_CLAUDE_CODE_HANDOFF.md` (v2).

- UI is already designed: built from `../Invoice_Auditor_UX_Mockups.html` + `../Invoice_Auditor_Design_Handoff.md`. Don't redesign — match the tokens, components, screens, states.
- All AI runs on a **local self-hosted Qwen** model; no external model calls by default (egress guard enforces this).
- The model **self-learns**: human dispositions → labels → (LoRA fine-tune → eval gate → promote) → serve for future auditing.
- Invoices come from a **separate AP tool** (not TRACK) — use `APClient` + mock until confirmed.
- **Humans own money decisions & high-value rejections** (agent recommends a hold, AP executes); everything audited **with model version**; **region-scoped** access (a Regional President sees only their brands).

Build Phase 0 (cross-brand visibility) first, then Phase 1 (detection + disposition capture). Ask before enabling auto-reject in production, wiring a real payment-hold, or sending any data to a non-local model.

See `DECISIONS.md` for the offline-first build choices (SQLite, offline Qwen narrator, served UI).
