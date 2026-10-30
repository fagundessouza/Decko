# Decko

Modular ERP and POS platform built around installable business modules: a company picks its
segment, and the system configures itself for that segment — in the spirit of Odoo, but built on a
modern, lightweight stack.

Commercial, sold by subscription. See [`docs/NEGOCIO.md`](docs/NEGOCIO.md) for the model and
where the product stands.

## Why

Small and mid-sized businesses in Brazil run on legacy management software that is slow, hard to
read and painful to operate — checkout queues stall waiting for a QR code, stock entry is typed in
by hand one item at a time, and compliance paperwork is still filled on carbon-copy pads.

Decko targets that gap, starting from real documents and real operations rather than assumptions.

## Status

Early development — foundation phase. See [`docs/ROADMAP.md`](docs/ROADMAP.md).

The first vertical module is **Agro**: it digitizes the spraying operation report
(*Planejamento Operacional*) that Brazilian agricultural drone operators are required to file,
automatically capturing GPS coordinates and the weather readings that are today written down by
hand — and preserving them as legally defensible evidence against spray drift claims.

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
docs/       negocio · architecture · roadmap · brand · discovery · adr · benchmark
```

## Documentation

| | |
|---|---|
| [NEGOCIO.md](docs/NEGOCIO.md) | Positioning, where the product stands, and what is missing to sell it |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the system is built, and why |
| [ROADMAP.md](docs/ROADMAP.md) | Phases and current progress |
| [benchmark/](docs/benchmark/) | Odoo 20 architecture audit, and how Decko compares |
| [BRAND.md](docs/BRAND.md) | Color semantics, typography, accessibility rules |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Branching model and conventions |
| [CLAUDE.md](CLAUDE.md) | Project rules for AI-assisted development |

Working documentation is written in Brazilian Portuguese: the domain is Brazilian regulation
(MAPA, tax law) and precision matters more than reach.
