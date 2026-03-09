# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vanta Billing is a Peruvian electronic invoicing (facturación electrónica) **microservice** built with FastAPI. It manages clients, generates UBL 2.1 XML documents (invoices, boletas, and dispatch guides), signs them with digital certificates, and submits them to SUNAT (Peru's tax authority) via SOAP.

This is a **standalone microservice** designed to be consumed by other applications (monoliths, frontends, other services) via its REST API.

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

- **`app/routers/`** — FastAPI route handlers:
  - `clients.py` — Registration, profile, certificate upload, key rotation.
  - `documents.py` — Invoice/receipt creation, listing, retry, status check.
  - `dispatch_guides.py` — Guías de Remisión (GRR remitente + GRT transportista).
- **`app/services/billing.py`** — Invoice/receipt orchestration: translates user input → SUNAT catalog codes, calculates IGV (tax), persists document, builds XML, signs it, generates QR, sends to SUNAT.
- **`app/services/gr_billing.py`** — Dispatch guide orchestration: persist → build DespatchAdvice XML → sign → generate QR → send to SUNAT (no tax calculation).
- **`app/services/xml_builder.py`** — Builds UBL 2.1 Invoice XML using `lxml`.
- **`app/services/xml_builder_gr.py`** — Builds UBL 2.1 DespatchAdvice XML for dispatch guides.
- **`app/services/xml_signer.py`** — Signs XML with client's `.pfx`/`.p12` certificate via `signxml`. Shared by invoices and dispatch guides.
- **`app/services/qr_generator.py`** — QR code generation. `build_qr_text` for invoices (includes IGV/totals), `build_dispatch_guide_qr_text` for GRs (no monetary fields). Shared `generate_qr_image` returns base64 PNG.
- **`app/services/integrations/sunat/`** — SOAP client for invoices/boletas and REST client for dispatch guides (GRE). REST uses OAuth2 with per-client `sunat_client_id`/`sunat_client_secret` (falls back to global env vars).
- **`app/services/crypto.py`** — Fernet encryption/decryption for sensitive fields, API key hashing.
- **`app/services/sunat_catalogs.py`** — SUNAT catalog code mappings (document types, tax types, unit codes, transport modalities, transfer reasons).
- **`app/models/`** — SQLAlchemy models: `Client`, `Document`, `DocumentItem`, `DocumentSeries`, `DispatchGuide`, `DispatchGuideItem`.
- **`app/schemas/`** — Pydantic schemas for request/response validation.

### Invoice/Receipt Flow

1. Client sends invoice/receipt data to `POST /api/v1/invoices` or `/receipts`
2. `billing.py` translates item types to SUNAT codes, calculates tax amounts
3. Document + items are persisted to DB with auto-incrementing correlative per series
4. UBL 2.1 XML is built, signed with client's certificate, QR code generated
5. Signed XML is sent to SUNAT via SOAP; CDR response is stored
6. Failed documents can be retried via `POST /documents/{id}/retry`

### Dispatch Guide Flow (Guías de Remisión)

1. Client sends transport data to `POST /api/v1/dispatch-guides/remitente` (GRR, type "09", series T) or `/transportista` (GRT, type "31", series V)
2. `gr_billing.py` translates enums to SUNAT catalog codes (no tax calculation needed)
3. If `related_document_id` is provided, the related invoice/receipt is resolved and its type/number are stored + included in the XML as `<cac:AdditionalDocumentReference>`
4. DispatchGuide + items persisted to DB with auto-incrementing correlative
4. DespatchAdvice-2 UBL XML is built, signed with client's certificate, QR code generated
5. Signed XML sent to SUNAT via REST API (OAuth2 token + POST document + poll ticket); CDR response stored
6. Failed guides can be retried via `POST /dispatch-guides/{id}/retry`

**GRR (Remitente):** Requires transport modality — `public` needs carrier RUC/name, `private` needs vehicle plate + driver info.
**GRT (Transportista):** Always requires vehicle plate, driver info, and shipper (remitente) info.

### Exception Hierarchy

All custom exceptions inherit from `BillingError`. Specific subtypes (`SUNATError`, `XMLBuildError`, `XMLSignError`, `MissingCredentialsError`, `CDRParseError`) are mapped to HTTP status codes in `main.py` exception handlers.

## Integration Guide (for consuming services)

This microservice exposes a REST API under `http://<host>:8000/api/v1`. All business endpoints require a Bearer token (the client's API key).

### Setup Flow

1. **Register a client:** `POST /api/v1/clients` with `{ ruc, razon_social, ... }` → returns `api_key` (save it, shown only once)
2. **Upload certificate:** `POST /api/v1/clients/me/certificate` with `.pfx` file + password
3. **Configure SOL credentials:** `PUT /api/v1/clients/me` with `{ sol_user, sol_password }`
4. **Configure SUNAT REST credentials (required for dispatch guides):** `PUT /api/v1/clients/me` with `{ sunat_client_id, sunat_client_secret }` — each client must register their own application in SUNAT SOL portal (Menu SOL → Empresa → API REST) to obtain these. Falls back to global `SUNAT_REST_CLIENT_ID`/`SUNAT_REST_KEY` if not set per-client.
5. **Optionally set default series:** `PUT /api/v1/clients/me` with `{ serie_factura, serie_boleta, serie_grr, serie_grt }`

### Issuing Documents

All `POST` endpoints are async — they create, sign, and send to SUNAT in a single call, returning the full result including CDR response.

```
# Invoices (Facturas)
POST /api/v1/invoices
Authorization: Bearer <api_key>
{ "customer_doc_type": "ruc", "customer_doc_number": "20123456789",
  "customer_name": "...", "items": [{ "description": "...", "quantity": 1,
  "item_type": "product", "unit_price": 100.00, "tax_type": "gravado" }] }

# Receipts (Boletas)
POST /api/v1/receipts  (same structure, customer_doc_type defaults to "dni")

# Dispatch Guides — Remitente (GRR)
POST /api/v1/dispatch-guides/remitente
{ "transfer_reason": "venta", "transport_modality": "private",
  "transfer_date": "2026-03-05", "gross_weight": "150",
  "departure_address": "...", "departure_ubigeo": "150101",
  "arrival_address": "...", "arrival_ubigeo": "150201",
  "recipient_doc_type": "ruc", "recipient_doc_number": "20123456789",
  "recipient_name": "...", "vehicle_plate": "ABC-123",
  "driver_doc_type": "dni", "driver_doc_number": "12345678",
  "driver_name": "...", "driver_license": "Q12345678",
  "related_document_id": "uuid-of-invoice (optional)",
  "items": [{ "description": "Producto X", "quantity": 10, "unit_code": "NIU" }] }

# Dispatch Guides — Transportista (GRT)
POST /api/v1/dispatch-guides/transportista
(same as GRR but requires shipper_* fields and always requires vehicle/driver)
# Both GRR and GRT accept optional "related_document_id" to link to an existing invoice/receipt.
```

### Querying & Retry

```
GET  /api/v1/documents                        # List invoices/receipts
GET  /api/v1/documents/{id}                   # Detail with XML, CDR, items
GET  /api/v1/documents/{id}/status            # Query SUNAT live status
POST /api/v1/documents/{id}/retry             # Retry failed submission

GET  /api/v1/dispatch-guides                  # List dispatch guides
GET  /api/v1/dispatch-guides/{id}             # Detail
GET  /api/v1/dispatch-guides/{id}/status      # Query SUNAT live status
POST /api/v1/dispatch-guides/{id}/retry       # Retry failed submission
```

### Correlativos y Reintentos (IMPORTANTE)

El microservicio protege los correlativos para evitar saltos en la numeración SUNAT. El comportamiento varía según **dónde** ocurra el error:

**Fallo pre-SUNAT (XML build, firma):** El microservicio hace rollback completo de la transacción. No se persiste documento ni se consume correlativo. El caller puede reintentar con `POST /invoices` (o `/receipts`, `/dispatch-guides/*`) de forma segura — obtendrá el mismo correlativo.

**Fallo en envío SUNAT (error de red, rechazo):** El documento se persiste con status `ERROR` o `REJECTED`, con su XML firmado. El correlativo **sí** se consume porque el documento ya fue construido y potencialmente enviado.

**Flujo correcto para el caller (Rails):**

```
1. POST /api/v1/invoices → respuesta exitosa (status: ACCEPTED)
   ✅ Todo OK. Guardar el document.id y los datos.

2. POST /api/v1/invoices → HTTP 500 (XML build/sign error)
   ⚠️ No se consumió correlativo. No se creó documento.
   → Corregir los datos y volver a llamar POST /invoices.

3. POST /api/v1/invoices → HTTP 502 (SUNAT error) o status: ERROR/REJECTED
   ⚠️ Se consumió correlativo. El documento existe con id.
   → GUARDAR el document.id devuelto en la respuesta.
   → Para reintentar: POST /documents/{id}/retry (NO crear nuevo documento).
   → El retry reenvía el MISMO XML con el MISMO correlativo.
```

**Regla clave:** Cuando el HTTP status es 502 o el documento viene con status `ERROR`/`REJECTED`, el caller **DEBE** guardar el `id` del documento y usar el endpoint `/retry` en vez de crear un documento nuevo. Crear un documento nuevo en este caso quemaría un correlativo adicional.

Los mismos endpoints de retry existen para guías de remisión: `POST /dispatch-guides/{id}/retry`.

### Response Status Values

`CREATED` → `SIGNED` → `SENT` → `ACCEPTED` / `REJECTED` / `ERROR`

### SUNAT Catalog Quick Reference

- **Document types:** `01` Factura, `03` Boleta, `09` GR Remitente, `31` GR Transportista
- **Series prefixes:** `F` Factura, `B` Boleta, `T` GR Remitente, `V` GR Transportista
- **Transport modality (Cat. 18):** `public` (carrier handles transport), `private` (own vehicle)
- **Transfer reasons (Cat. 20):** `venta`, `compra`, `traslado_entre_establecimientos`, `importacion`, `exportacion`, `otros`
- **Tax types (Cat. 07):** `gravado` (18% IGV), `exonerado`, `inafecto`
- **Item types:** `product` (NIU), `service` (ZZ)

## Configuration

Environment variables loaded via `pydantic-settings` from `.env` (see `.env.example`). Key vars:

- `DATABASE_URL` — PostgreSQL connection string
- `ENCRYPTION_KEY` — Fernet key for encrypting SOL credentials and certificates
- `SUNAT_SOAP_URL` — SUNAT SOAP endpoint for invoices/boletas (e.g. `https://e-factura.sunat.gob.pe/ol-ti-itcpfegem`)
- `SUNAT_CONSULT_URL` — SUNAT status query endpoint (production only)
- `SUNAT_REST_CLIENT_ID` — Global fallback OAuth2 client ID for SUNAT REST API (dispatch guides). Per-client credentials take priority.
- `SUNAT_REST_KEY` — Global fallback OAuth2 client secret for SUNAT REST API. Per-client credentials take priority.
- `SUNAT_REST_TOKEN_URL` — SUNAT OAuth2 token endpoint (e.g. `https://api-seguridad.sunat.gob.pe/v1/clientessol`)
- `SUNAT_REST_API_URL` — SUNAT REST API base URL (e.g. `https://api-cpe.sunat.gob.pe/v1`)
- `IGV_RATE` — Tax rate (default `0.18`)

**Important:** Invoices use SUNAT **SOAP API** (`SUNAT_SOAP_URL`). Dispatch guides use SUNAT **REST API** (`SUNAT_REST_*` vars) with OAuth2 authentication. Each client's `sunat_client_id`/`sunat_client_secret` (stored encrypted in DB) are used first; the global env vars are fallback only.

### SUNAT REST API Credentials (Per-Client)

SUNAT's REST API for dispatch guides (GRE) requires OAuth2 credentials that are **scoped per RUC**. Each client (company/RUC) must register their own application in SUNAT's SOL portal to obtain a `client_id` and `client_secret`. One company's credentials **cannot** authenticate requests for a different RUC.

**Architecture:** `sunat_client_id` and `sunat_client_secret` are stored encrypted (Fernet) in the `clients` table. The REST client (`rest_client.py:get_sunat_token`) uses per-client values if available, otherwise falls back to global `SUNAT_REST_CLIENT_ID`/`SUNAT_REST_KEY` from settings. The global fallback only works if all clients share the same RUC.

**Client registration flow:**
1. Client goes to SUNAT SOL → Menu → Empresa → API REST
2. Creates a new application, obtains `client_id` and `client_secret`
3. Configures them via `PUT /api/v1/clients/me` with `{ sunat_client_id, sunat_client_secret }`
4. `GET /api/v1/clients/me` shows `has_sunat_rest_credentials: true/false`

Docker Compose exposes Postgres on host port **5434** (not 5432).

Alembic reads `DATABASE_URL` from the environment (overridden in `alembic/env.py`), not from `alembic.ini`.
