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
  - `credit_notes.py` — Credit note creation, listing, retry.
  - `dispatch_guides.py` — Guías de Remisión (GRR remitente + GRT transportista).
- **`app/services/billing.py`** — Invoice/receipt orchestration: translates user input → SUNAT catalog codes, extracts base price from IGV-inclusive `unit_price`, calculates IGV, persists document, builds XML, signs it, generates QR, sends to SUNAT.
- **`app/services/gr_billing.py`** — Dispatch guide orchestration: persist → build DespatchAdvice XML → sign → generate QR → send to SUNAT (no tax calculation).
- **`app/services/cn_billing.py`** — Credit note orchestration: validate reference → calculate → persist → build CreditNote XML → sign → QR → send to SUNAT.
- **`app/services/xml_builder.py`** — Builds UBL 2.1 Invoice XML using `lxml`.
- **`app/services/xml_builder_cn.py`** — Builds UBL 2.1 CreditNote XML (with `DiscrepancyResponse` + `BillingReference`).
- **`app/services/xml_builder_gr.py`** — Builds UBL 2.1 DespatchAdvice XML for dispatch guides.
- **`app/services/xml_signer.py`** — Signs XML with client's `.pfx`/`.p12` certificate via `signxml`. Shared by invoices and dispatch guides.
- **`app/services/qr_generator.py`** — QR code generation. `build_qr_text` for invoices (includes IGV/totals), `build_dispatch_guide_qr_text` for GRs (no monetary fields). Shared `generate_qr_image` returns base64 PNG.
- **`app/services/integrations/sunat/`** — SOAP client for invoices/boletas and REST client for dispatch guides (GRE). REST uses OAuth2 with per-client `sunat_client_id`/`sunat_client_secret` (falls back to global env vars).
- **`app/services/crypto.py`** — Fernet encryption/decryption for sensitive fields, API key hashing.
- **`app/services/sunat_catalogs.py`** — SUNAT catalog code mappings (document types, tax types, unit codes, transport modalities, transfer reasons, credit note reason codes).
- **`app/models/`** — SQLAlchemy models: `Client`, `Document`, `DocumentItem`, `DocumentInstallment`, `DocumentSeries`, `DispatchGuide`, `DispatchGuideItem`.
- **`app/schemas/`** — Pydantic schemas for request/response validation.

### Pricing: unit_price + unit_price_without_tax (IMPORTANT)

Items support two pricing fields:

- **`unit_price`** (required): Price **WITH IGV** (precio de venta al público). Always sent.
- **`unit_price_without_tax`** (optional, nullable): Explicit base price **WITHOUT IGV**. When provided, the microservice uses it directly — no division, no rounding amplification.

**When `unit_price_without_tax` IS provided (recommended):**
The microservice uses it as the base price directly. Both caller and microservice compute identical totals because the same input produces the same deterministic calculation: `line_ext = round(qty × base, 2)`, `igv = round(line_ext × 0.18, 2)`.

Example: `unit_price: 11.80, unit_price_without_tax: 10.00, tax_type: "gravado"` → `base: 10.00`, `igv: 1.80 × qty`, `total: 11.80 × qty`.

**When `unit_price_without_tax` is NOT provided (backward compatible):**
Falls back to extracting the base price via `unit_price / 1.18`. This can cause rounding discrepancies with high quantities (e.g., `3.10 / 1.18 = 2.627... → 2.63`, amplified by qty). Existing clients that only send `unit_price` continue working as before.

- **Gravado items:** `base_price = unit_price_without_tax ?? (unit_price / 1.18)`
- **Exonerado/Inafecto items:** `base_price = unit_price_without_tax ?? unit_price` — no IGV component.

This applies to invoices, receipts, and credit notes. The `unit_price_without_tax` field is stored in the `document_items` table (nullable) for audit purposes.

### Invoice/Receipt Flow

1. Client sends invoice/receipt data to `POST /api/v1/invoices` or `/receipts`
2. `billing.py` translates item types to SUNAT codes, extracts base price from IGV-inclusive `unit_price`, calculates IGV
3. Document + items (+ installments if credit) are persisted to DB with auto-incrementing correlative per series
4. UBL 2.1 XML is built with payment terms (`Contado` or `Credito` + cuotas), signed with client's certificate, QR code generated
5. Signed XML is sent to SUNAT via SOAP; CDR response is stored
6. Failed documents can be retried via `POST /documents/{id}/retry`

### Credit Note Flow (Notas de Crédito)

Credit notes apply to both **facturas** and **boletas**. Each has its own series managed independently.

1. Client sends credit note data to `POST /api/v1/credit-notes` with `reference_document_id` (UUID of the original invoice/receipt). `series` is optional — if omitted, the microservice auto-resolves it from the client config based on the referenced document type (factura → `serie_nota_credito_factura`, boleta → `serie_nota_credito_boleta`).
2. `cn_billing.py` validates the reference document exists, belongs to the client, and is type `"01"` (factura) or `"03"` (boleta)
3. Customer info and currency are inherited from the referenced document
4. Items are calculated with the same IGV-extraction logic as invoices
5. CreditNote UBL 2.1 XML is built (with `DiscrepancyResponse` + `BillingReference`), signed, QR generated
6. Signed XML sent to SUNAT via SOAP (document type `"07"`); CDR response stored
7. Failed credit notes can be retried via `POST /credit-notes/{id}/retry`

**Series configuration:** Clients must configure `serie_nota_credito_factura` (e.g. `FC01`) and `serie_nota_credito_boleta` (e.g. `BC01`) via `PUT /api/v1/clients/me`. The series is auto-resolved from the client config based on the referenced document type. The caller can optionally override it by sending `series` explicitly.

**Partial credit notes:** A credit note can include a subset of items from the original document. Multiple credit notes can reference the same invoice/boleta.

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
5. **Set default series:** `PUT /api/v1/clients/me` with `{ serie_factura, serie_boleta, serie_grr, serie_grt, serie_nota_credito_factura, serie_nota_credito_boleta }`

### Issuing Documents

All `POST` endpoints are async — they create, sign, and send to SUNAT in a single call, returning the full result including CDR response.

```
# Invoices (Facturas) — Contado, with unit_price_without_tax (recommended)
POST /api/v1/invoices
Authorization: Bearer <api_key>
{ "customer_doc_type": "ruc", "customer_doc_number": "20123456789",
  "customer_name": "...", "items": [{ "description": "...", "quantity": 1,
  "item_type": "product", "unit_price": 118.00,
  "unit_price_without_tax": 100.00, "tax_type": "gravado" }] }

# Invoices (Facturas) — Contado, backward compatible (no unit_price_without_tax)
POST /api/v1/invoices
Authorization: Bearer <api_key>
{ "customer_doc_type": "ruc", "customer_doc_number": "20123456789",
  "customer_name": "...", "items": [{ "description": "...", "quantity": 1,
  "item_type": "product", "unit_price": 118.00, "tax_type": "gravado" }] }

# Invoices (Facturas) — Crédito con cuotas
POST /api/v1/invoices
Authorization: Bearer <api_key>
{ "customer_doc_type": "ruc", "customer_doc_number": "20123456789",
  "customer_name": "...",
  "payment_condition": "credito",
  "installments": [
    { "amount": 59.00, "due_date": "2026-04-09" },
    { "amount": 59.00, "due_date": "2026-05-09" }
  ],
  "items": [{ "description": "...", "quantity": 1,
  "item_type": "product", "unit_price": 118.00,
  "unit_price_without_tax": 100.00, "tax_type": "gravado" }] }

# Receipts (Boletas)
POST /api/v1/receipts  (same structure, customer_doc_type defaults to "dni")
# Receipts also support payment_condition + installments, same as invoices.

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

# Credit Notes (Notas de Crédito) — para Facturas
POST /api/v1/credit-notes
Authorization: Bearer <api_key>
{ "reference_document_id": "uuid-of-the-original-invoice",
  "reason_code": "anulacion_de_la_operacion",
  "description": "Anulación por montos incorrectos",
  "items": [{ "description": "...", "quantity": 1,
  "item_type": "product", "unit_price": 5900.00,
  "unit_price_without_tax": 5000.00, "tax_type": "gravado" }] }

# Credit Notes (Notas de Crédito) — para Boletas
POST /api/v1/credit-notes
Authorization: Bearer <api_key>
{ "reference_document_id": "uuid-of-the-original-boleta",
  "reason_code": "devolucion_total",
  "description": "Devolución total del producto",
  "items": [{ "description": "...", "quantity": 1,
  "item_type": "product", "unit_price": 118.00,
  "unit_price_without_tax": 100.00, "tax_type": "gravado" }] }

# series is OPTIONAL — auto-resolved from client config based on the referenced document type
#   (factura → serie_nota_credito_factura e.g. FC01, boleta → serie_nota_credito_boleta e.g. BC01).
#   Can be overridden by sending "series" explicitly.
# Customer info and currency are inherited from the referenced document.
# Credit notes can reference a subset of items — you don't need to include all items from the original document.
# A single invoice/boleta can have multiple credit notes.
```

### Payment Conditions (Condición de Venta)

Invoices and receipts support two payment conditions via the `payment_condition` field:

- **`"contado"`** (default) — Cash sale. No installments. This is the default when `payment_condition` is omitted, so existing integrations work without changes.
- **`"credito"`** — Credit sale. Requires `installments` array with at least one entry.

**Installment rules:**
- Each installment has `amount` (Decimal, > 0) and `due_date` (date, format `YYYY-MM-DD`).
- The sum of all installment amounts **must equal** the document's `total_amount` (total with IGV).
- Installments are numbered automatically (`Cuota001`, `Cuota002`, ...) in the XML sent to SUNAT.
- If `payment_condition` is `"contado"`, sending `installments` will return a validation error.
- If `payment_condition` is `"credito"`, omitting `installments` will return a validation error.

**XML structure generated for SUNAT (Resolución 193-2020/SUNAT):**

```xml
<!-- Crédito: bloque principal con monto pendiente total -->
<cac:PaymentTerms>
  <cbc:ID>FormaPago</cbc:ID>
  <cbc:PaymentMeansID>Credito</cbc:PaymentMeansID>
  <cbc:Amount currencyID="PEN">118.00</cbc:Amount>
</cac:PaymentTerms>
<!-- Un bloque por cada cuota -->
<cac:PaymentTerms>
  <cbc:ID>FormaPago</cbc:ID>
  <cbc:PaymentMeansID>Cuota001</cbc:PaymentMeansID>
  <cbc:Amount currencyID="PEN">59.00</cbc:Amount>
  <cbc:PaymentDueDate>2026-04-09</cbc:PaymentDueDate>
</cac:PaymentTerms>
<cac:PaymentTerms>
  <cbc:ID>FormaPago</cbc:ID>
  <cbc:PaymentMeansID>Cuota002</cbc:PaymentMeansID>
  <cbc:Amount currencyID="PEN">59.00</cbc:Amount>
  <cbc:PaymentDueDate>2026-05-09</cbc:PaymentDueDate>
</cac:PaymentTerms>
```

**Response fields:** `DocumentRead` includes `payment_condition`. `DocumentDetail` includes `payment_condition` and `installments[]` (each with `id`, `installment_number`, `amount`, `due_date`).

**DB schema:** `documents.payment_condition` (VARCHAR, default `"contado"`). Installments stored in `document_installments` table (`id`, `document_id`, `installment_number`, `amount`, `due_date`).

### Client Series Configuration

Series are stored in the `clients` table and configured via `PUT /api/v1/clients/me`:

| Field | Example | Document Type |
|---|---|---|
| `serie_factura` | `F001` | Facturas (01) |
| `serie_boleta` | `B001` | Boletas (03) |
| `serie_nota_credito_factura` | `FC01` | NC de Facturas (07) |
| `serie_nota_credito_boleta` | `BC01` | NC de Boletas (07) |
| `serie_grr` | `T001` | GR Remitente (09) |
| `serie_grt` | `V001` | GR Transportista (31) |

Each series has its own independent correlative counter (auto-incrementing, managed in `document_series` table). The caller sends the `series` field in each document creation request.

### Credit Note Reason Codes (Catálogo 09)

| Value in API | SUNAT Code | Description |
|---|---|---|
| `anulacion_de_la_operacion` | 01 | Anulación de la operación |
| `anulacion_por_error_en_el_ruc` | 02 | Anulación por error en el RUC |
| `correccion_por_error_en_la_descripcion` | 03 | Corrección por error en la descripción |
| `descuento_global` | 04 | Descuento global |
| `descuento_por_item` | 05 | Descuento por ítem |
| `devolucion_total` | 06 | Devolución total |
| `devolucion_por_item` | 07 | Devolución por ítem |
| `bonificacion` | 08 | Bonificación |
| `disminucion_en_el_valor` | 09 | Disminución en el valor |
| `otros_conceptos` | 10 | Otros conceptos |
| `ajustes_de_operaciones_de_exportacion` | 11 | Ajustes de operaciones de exportación |
| `ajustes_afectos_al_ivap` | 12 | Ajustes afectos al IVAP |
| `correccion_del_monto_neto_pendiente_de_pago` | 13 | Corrección del monto neto pendiente de pago / cuotas |

The `description` field is **required by SUNAT** (free text provided by the user explaining the reason).

### Querying & Retry

```
GET  /api/v1/documents                        # List invoices/receipts
GET  /api/v1/documents/{id}                   # Detail with XML, CDR, items
GET  /api/v1/documents/{id}/status            # Query SUNAT live status
POST /api/v1/documents/{id}/retry             # Retry failed submission

GET  /api/v1/credit-notes                     # List credit notes
GET  /api/v1/credit-notes/{id}               # Detail with XML, CDR, items
POST /api/v1/credit-notes/{id}/retry         # Retry failed submission

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

Los mismos endpoints de retry existen para guías de remisión (`POST /dispatch-guides/{id}/retry`) y notas de crédito (`POST /credit-notes/{id}/retry`).

### Response Status Values

`CREATED` → `SIGNED` → `SENT` → `ACCEPTED` / `REJECTED` / `ERROR`

### SUNAT Catalog Quick Reference

- **Document types:** `01` Factura, `03` Boleta, `07` Nota de Crédito, `09` GR Remitente, `31` GR Transportista
- **Series prefixes:** `F` Factura, `B` Boleta, `FC` NC Factura, `BC` NC Boleta, `T` GR Remitente, `V` GR Transportista
- **Payment condition:** `contado` (cash), `credito` (credit with installments) — Resolución 193-2020/SUNAT
- **Transport modality (Cat. 18):** `public` (carrier handles transport), `private` (own vehicle)
- **Transfer reasons (Cat. 20):** `venta`, `compra`, `traslado_entre_establecimientos`, `importacion`, `exportacion`, `otros`
- **Tax types (Cat. 07):** `gravado` (18% IGV), `exonerado`, `inafecto`
- **Item types:** `product` (NIU), `service` (ZZ)
- **Credit note reasons (Cat. 09):** `anulacion_de_la_operacion`, `anulacion_por_error_en_el_ruc`, `correccion_por_error_en_la_descripcion`, `descuento_global`, `descuento_por_item`, `devolucion_total`, `devolucion_por_item`, `bonificacion`, `disminucion_en_el_valor`, `otros_conceptos`, `correccion_del_monto_neto_pendiente_de_pago`

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
