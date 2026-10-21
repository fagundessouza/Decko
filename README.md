# Decko

Modular ERP and POS platform built around installable business modules: a company picks its
segment, and the system configures itself for that segment — in the spirit of Odoo, but built on a
modern, lightweight stack.

Open Core: the platform core is open source; managed hosting and advanced modules are commercial.

## Why

Small and mid-sized businesses in Brazil run on legacy management software that is slow, hard to
read and painful to operate — checkout queues stall waiting for a QR code, stock entry is typed in
by hand one item at a time, and compliance paperwork is still filled on carbon-copy pads.

Decko targets that gap, starting from real documents and real operations rather than assumptions.

## Status

Early development. The foundation is in place and the first vertical module runs end to end;
neither has been used in a real operation yet. Phase by phase: [`docs/ROADMAP.md`](docs/ROADMAP.md).

**Foundation** — authentication with Argon2id and rotating refresh tokens, roles and permissions
assembled from module manifests, an audit trail, and tenant isolation enforced by PostgreSQL Row
Level Security and proven by tests against a real database.

**Agro** — the first vertical module. It digitizes the spraying operation report
(*Planejamento Operacional*) that Brazilian agricultural drone operators are required to file,
automatically capturing GPS coordinates and the weather readings that are today written down by
hand — and preserving them as legally defensible evidence against spray drift claims.

A plan is filled in on a phone, one decision per screen; the device supplies the coordinate; the
weather for that coordinate and time is fetched and stored with its full provenance; readings
outside the application window are flagged with *which* limit was broken; and the report is issued
as a print-ready PDF that follows the structure of the paper form it replaces.

Still open: product and prescription registration, monthly consolidation, and the field validation
that decides whether the printed document can actually replace the pad.

Requirements come from a form currently in production use at an agricultural drone company:
[`docs/discovery/agro-planejamento-operacional.md`](docs/discovery/agro-planejamento-operacional.md).

## Architecture

A modular monolith. Modules are self-contained units with their own backend, frontend and
migrations, declared through a manifest and activated per tenant. Tenant isolation is enforced by
PostgreSQL Row Level Security rather than application-level filtering.

Details and rationale: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Stack

**Backend** — Python, FastAPI, PostgreSQL, Alembic, Redis, MinIO, Qdrant
**Frontend** — React, Vite, TypeScript, Tailwind; PWA with offline support
**Packaging** — Capacitor (Android), Tauri (desktop)
**AI** — Ollama, local LLMs, embeddings, RAG, Tesseract OCR
**Observability** — Prometheus, Grafana, Jaeger
**Containers** — Podman

## Repository layout

```
apps/       api (FastAPI host) · web (React shell) · worker (async jobs)
modules/    core · agro · distribuidora
packages/   tokens (design tokens) · ui (shared components)
infra/      compose · observability
docs/       architecture · roadmap · brand · discovery · adr
```

## Documentation

| | |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the system is built, and why |
| [ROADMAP.md](docs/ROADMAP.md) | Phases and current progress |
| [agro-api.md](docs/agro-api.md) | Agro endpoints and the permission each one requires |
| [BRAND.md](docs/BRAND.md) | Color semantics, typography, accessibility rules |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Branching model and conventions |
| [CLAUDE.md](CLAUDE.md) | Project rules for AI-assisted development |

Working documentation is written in Brazilian Portuguese: the domain is Brazilian regulation
(MAPA, tax law) and precision matters more than reach.
