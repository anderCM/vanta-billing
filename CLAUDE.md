# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vanta Billing is a Peruvian electronic invoicing (facturación electrónica) API built with FastAPI. It manages clients, generates UBL 2.1 XML documents (invoices/boletas), signs them with digital certificates, and submits them to SUNAT (Peru's tax authority) via SOAP.

## Common Commands

```bash
# Start services (Postgres + app with hot reload)
docker compose up

# Run tests
docker compose run --rm test
# Or locally (requires Postgres running):
pytest -v
pytest --cov=app --cov-report=term-missing

# Run a single test
pytest tests/test_health.py -v
pytest -k "test_name" -v

# Database migrations
alembic upgrade head          # apply all migrations
alembic revision --autogenerate -m "description"  # create new migration

# Run app locally (without Docker)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Architecture

**Stack:** Python 3.12, FastAPI, SQLAlchemy (sync), PostgreSQL 16, Alembic, httpx (async SUNAT calls).

**API prefix:** All business endpoints are under `/api/v1`. Health check is at `/health`.

**Authentication:** Bearer token via `HTTPBearer`. Clients authenticate with API keys that are hashed (SHA-256) and looked up in `dependencies.py:get_current_client`. SOL credentials and certificates are encrypted at rest with Fernet (`services/crypto.py`).

### Key Layers

- **`app/routers/`** — FastAPI route handlers. `clients.py` (registration, profile, certificate upload, key rotation) and `documents.py` (invoice/receipt creation, listing, retry, status check).
- **`app/services/billing.py`** — Core billing orchestration: translates user input → SUNAT catalog codes, calculates IGV (tax), persists document, builds XML, signs it, generates QR, sends to SUNAT. This is the main business logic file.
- **`app/services/xml_builder.py`** — Builds UBL 2.1 XML using `lxml`.
- **`app/services/xml_signer.py`** — Signs XML with client's `.pfx`/`.p12` certificate via `signxml`.
- **`app/services/integrations/sunat.py`** — SOAP client for SUNAT submission and status queries using `httpx`.
- **`app/services/crypto.py`** — Fernet encryption/decryption for sensitive fields, API key hashing.
- **`app/services/sunat_catalogs.py`** — SUNAT catalog code mappings (document types, tax types, unit codes).
- **`app/models/`** — SQLAlchemy models: `Client`, `Document`, `DocumentItem`, `DocumentSeries`.
- **`app/schemas/`** — Pydantic schemas for request/response validation.

### Document Flow

1. Client sends invoice/receipt data to `POST /api/v1/invoices` or `/receipts`
2. `billing.py` translates item types to SUNAT codes, calculates tax amounts
3. Document + items are persisted to DB with auto-incrementing correlative per series
4. UBL 2.1 XML is built, signed with client's certificate, QR code generated
5. Signed XML is sent to SUNAT via SOAP; CDR response is stored
6. Failed documents can be retried via `POST /documents/{id}/retry`

### Exception Hierarchy

All custom exceptions inherit from `BillingError`. Specific subtypes (`SUNATError`, `XMLBuildError`, `XMLSignError`, `MissingCredentialsError`, `CDRParseError`) are mapped to HTTP status codes in `main.py` exception handlers.

## Configuration

Environment variables loaded via `pydantic-settings` from `.env` (see `.env.example`). Key vars: `DATABASE_URL`, `ENCRYPTION_KEY` (Fernet key), `SUNAT_SOAP_URL`, `IGV_RATE`.

Docker Compose exposes Postgres on host port **5434** (not 5432).

Alembic reads `DATABASE_URL` from the environment (overridden in `alembic/env.py`), not from `alembic.ini`.
