# Vanta Billing - Error Catalog

Reference for developers integrating with the Vanta Billing API.

All errors return JSON with this structure:

```json
{
  "detail": "Descriptive error message"
}
```

For validation errors (HTTP 422), FastAPI returns a structured format:

```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "Description of the validation error",
      "type": "error_type"
    }
  ]
}
```

The HTTP status code travels in the response header, not in the body.

---

## Table of Contents

1. [Authentication (401, 403)](#1-authentication--authorization)
2. [Validation (422)](#2-validation-errors)
3. [Client Management (400, 409)](#3-client-management)
4. [Documents - Invoices & Receipts (400, 404, 422)](#4-documents---invoices--receipts)
5. [Dispatch Guides (400, 404, 422)](#5-dispatch-guides---guias-de-remision)
6. [SUNAT Integration (502)](#6-sunat-integration)
7. [Internal Errors (500)](#7-internal-errors)
8. [Document Status Flow](#8-document-status-flow)

---

## 1. Authentication & Authorization

### HTTP 401 - Unauthorized

| Error | Message | Cause |
|-------|---------|-------|
| API key invalid | `Invalid or inactive API key` | The Bearer token does not match any registered client, or the client account is deactivated (`is_active = false`). |

**Example:**

```
GET /api/v1/documents
Authorization: Bearer bad_key_here

→ 401 {"detail": "Invalid or inactive API key"}
```

### HTTP 403 - Forbidden

| Error | Message | Cause |
|-------|---------|-------|
| IP restricted (integrator) | `IP not authorized for this client's integrator` | The client belongs to an integrator and the request IP is not in the integrator's allowed IPs list. |
| IP restricted (global) | `IP not allowed` | The request IP is not whitelisted for any active integrator (middleware-level check). |

---

## 2. Validation Errors

### HTTP 422 - Unprocessable Entity

FastAPI automatically validates request bodies against Pydantic schemas. These errors return an array of individual field errors.

### 2.1 Client Creation (`POST /api/v1/clients`)

| Field | Constraint | Example Error |
|-------|-----------|---------------|
| `ruc` | Required, exactly 11 characters | `String should have at least 11 characters` |
| `razon_social` | Required, max 255 characters | `Field required` |
| `ubigeo` | Optional, max 6 characters | `String should have at most 6 characters` |

### 2.2 Client Update (`PUT /api/v1/clients/me`)

| Field | Constraint | Example Error |
|-------|-----------|---------------|
| `serie_factura` | Max 4 characters | `String should have at most 4 characters` |
| `serie_boleta` | Max 4 characters | `String should have at most 4 characters` |
| `serie_grr` | Max 4 characters | `String should have at most 4 characters` |
| `serie_grt` | Max 4 characters | `String should have at most 4 characters` |
| `send_email` | Boolean | `Input should be a valid boolean` |
| `generate_pdf` | Boolean | `Input should be a valid boolean` |

### 2.3 Invoice/Receipt Items (`items[]`)

| Field | Constraint | Example Error |
|-------|-----------|---------------|
| `description` | Required, max 500 characters | `Field required` |
| `quantity` | Required, must be > 0 | `Input should be greater than 0` |
| `item_type` | Required, one of: `product`, `service` | `Input should be 'product' or 'service'` |
| `unit_price` | Required, must be > 0 | `Input should be greater than 0` |
| `tax_type` | Required, one of: `gravado`, `exonerado`, `inafecto` | `Input should be 'gravado', 'exonerado' or 'inafecto'` |

### 2.4 Invoice (`POST /api/v1/invoices`)

| Field | Constraint | Example Error |
|-------|-----------|---------------|
| `customer_doc_number` | Required, max 20 characters | `Field required` |
| `customer_name` | Required, max 255 characters | `Field required` |
| `customer_doc_type` | One of: `ruc`, `dni` (default: `ruc`) | `Input should be 'ruc' or 'dni'` |
| `currency` | Max 3 characters (default: `PEN`) | `String should have at most 3 characters` |
| `series` | Optional, max 4 characters | `String should have at most 4 characters` |
| `items` | Required, at least 1 item | `List should have at least 1 item after validation, not 0` |

### 2.5 Receipt (`POST /api/v1/receipts`)

Same fields as Invoice. The only difference is `customer_doc_type` defaults to `dni` instead of `ruc`.

### 2.6 Dispatch Guide - GRR Remitente (`POST /api/v1/dispatch-guides/remitente`)

| Field | Constraint | Example Error |
|-------|-----------|---------------|
| `transfer_reason` | Required, one of: `venta`, `compra`, `traslado_entre_establecimientos`, `importacion`, `exportacion`, `otros` | `Input should be 'venta', 'compra', ...` |
| `transport_modality` | Required, one of: `public`, `private` | `Input should be 'public' or 'private'` |
| `transfer_date` | Required, format `YYYY-MM-DD` | `Field required` |
| `gross_weight` | Required | `Field required` |
| `weight_unit_code` | Max 5 characters (default: `KGM`) | `String should have at most 5 characters` |
| `departure_address` | Required, max 500 characters | `Field required` |
| `departure_ubigeo` | Required, exactly 6 characters | `String should have at least 6 characters` |
| `arrival_address` | Required, max 500 characters | `Field required` |
| `arrival_ubigeo` | Required, exactly 6 characters | `String should have at least 6 characters` |
| `recipient_doc_type` | One of: `ruc`, `dni` (default: `ruc`) | `Input should be 'ruc' or 'dni'` |
| `recipient_doc_number` | Required, max 20 characters | `Field required` |
| `recipient_name` | Required, max 255 characters | `Field required` |
| `items` | Required, at least 1 item | `List should have at least 1 item after validation, not 0` |

**Conditional validation by transport modality:**

| Modality | Required Fields | Error if Missing |
|----------|----------------|-----------------|
| `public` | `carrier_ruc`, `carrier_name` | `Value error, carrier_ruc and carrier_name required for public transport` |
| `private` | `vehicle_plate`, `driver_doc_number`, `driver_name`, `driver_license` | `Value error, vehicle_plate required for private transport` or `Value error, driver info required for private transport` |

### 2.7 Dispatch Guide - GRT Transportista (`POST /api/v1/dispatch-guides/transportista`)

Includes all fields from GRR (section 2.6) plus these **required** fields:

| Field | Constraint | Example Error |
|-------|-----------|---------------|
| `shipper_doc_type` | One of: `ruc`, `dni` (default: `ruc`) | `Input should be 'ruc' or 'dni'` |
| `shipper_doc_number` | Required, max 20 characters | `Field required` |
| `shipper_name` | Required, max 255 characters | `Field required` |
| `vehicle_plate` | Required, max 20 characters | `Field required` |
| `driver_doc_type` | One of: `ruc`, `dni` (default: `dni`) | `Input should be 'ruc' or 'dni'` |
| `driver_doc_number` | Required, max 20 characters | `Field required` |
| `driver_name` | Required, max 255 characters | `Field required` |
| `driver_license` | Required, max 50 characters | `Field required` |

### 2.8 Dispatch Guide Items (`items[]`)

| Field | Constraint | Example Error |
|-------|-----------|---------------|
| `description` | Required, max 500 characters | `Field required` |
| `quantity` | Required, must be > 0 | `Input should be greater than 0` |
| `unit_code` | Max 5 characters (default: `NIU`) | `String should have at most 5 characters` |

### 2.9 Query Parameters (Listing endpoints)

| Parameter | Constraint | Example Error |
|-----------|-----------|---------------|
| `page` | Integer >= 1 (default: 1) | `Input should be greater than or equal to 1` |
| `page_size` | Integer >= 1 and <= 100 (default: 20) | `Input should be less than or equal to 100` |
| `date_from` | Valid datetime format | `Input should be a valid datetime` |
| `date_to` | Valid datetime format | `Input should be a valid datetime` |

---

## 3. Client Management

### HTTP 400 - Bad Request

| Error | Message | Cause |
|-------|---------|-------|
| Invalid certificate file | `File must be a .pfx or .p12 certificate` | Uploaded file to `POST /api/v1/clients/me/certificate` does not have `.pfx` or `.p12` extension. |

### HTTP 409 - Conflict

| Error | Message | Cause |
|-------|---------|-------|
| Duplicate RUC | `A client with this RUC already exists` | Attempting to register a client with a RUC that is already registered. |

---

## 4. Documents - Invoices & Receipts

### HTTP 400 - Bad Request

| Error | Message | Cause |
|-------|---------|-------|
| Invalid status for retry | `Cannot retry document in status '{status}'` | `POST /api/v1/documents/{id}/retry` — document is in `CREATED`, `SENT`, or `ACCEPTED` status. Retry only works for `SIGNED`, `ERROR`, or `REJECTED`. |
| Missing signed XML | `Document has no signed XML to send` | `POST /api/v1/documents/{id}/retry` — the document was never successfully signed. |

### HTTP 404 - Not Found

| Error | Message | Cause |
|-------|---------|-------|
| Document not found | `Document not found` | The document ID does not exist or does not belong to the authenticated client. |

### HTTP 422 - Unprocessable Entity

| Error | Message | Cause |
|-------|---------|-------|
| No series configured | `No series provided and client has no default series configured` | No `series` field in the request body and the client has no default `serie_factura` (invoices) or `serie_boleta` (receipts). |
| Missing SOL credentials | `SOL credentials not configured` | Client has not configured `sol_user` and `sol_password`. Required before issuing documents. |
| Missing certificate | `Digital certificate not uploaded` | Client has not uploaded a `.pfx`/`.p12` digital certificate. Required before issuing documents. |

---

## 5. Dispatch Guides - Guias de Remision

### HTTP 400 - Bad Request

| Error | Message | Cause |
|-------|---------|-------|
| Invalid status for retry | `Cannot retry dispatch guide in status '{status}'` | Same as documents — retry only for `SIGNED`, `ERROR`, or `REJECTED`. |
| Missing signed XML | `Dispatch guide has no signed XML to send` | Guide was never successfully signed. |

### HTTP 404 - Not Found

| Error | Message | Cause |
|-------|---------|-------|
| Guide not found | `Dispatch guide not found` | The guide ID does not exist or does not belong to the authenticated client. |

### HTTP 422 - Unprocessable Entity

| Error | Message | Cause |
|-------|---------|-------|
| Invalid series prefix | `Series for document type {type} must start with '{prefix}'` | GRR (type `09`) must use series starting with `T`. GRT (type `31`) must use series starting with `V`. |
| No series configured | `No series provided and client has no default series configured` | No `series` in request and client has no default `serie_grr` (GRR) or `serie_grt` (GRT). |
| Missing SOL credentials | `SOL credentials not configured` | Same as documents. |
| Missing certificate | `Digital certificate not uploaded` | Same as documents. |

---

## 6. SUNAT Integration

All SUNAT errors return **HTTP 502 Bad Gateway** because they originate from communication with an external service.

### HTTP 502 - Bad Gateway

#### SOAP Errors (Invoices, Receipts, Status Queries)

| Error | Message Pattern | Cause |
|-------|----------------|-------|
| Invalid SOAP response | `Invalid SOAP XML response: {details}` | SUNAT returned malformed XML. |
| Missing SOAP body | `Missing SOAP Body in response` | SUNAT response did not include a SOAP Body element. |
| SOAP fault | `SOAP Fault [{fault_code}]: {fault_string}` | SUNAT rejected the request. The `fault_string` contains SUNAT's error message (e.g., invalid credentials, XML validation failure). |
| HTTP error | `SUNAT SOAP HTTP error: {status_code}` | SUNAT returned an unexpected HTTP status (not 200 or 500). |

#### CDR (Constancia de Recepcion) Parse Errors

| Error | Message Pattern | Cause |
|-------|----------------|-------|
| Invalid base64 | `Invalid base64 in CDR: {details}` | SUNAT's CDR response contains invalid base64 encoding. |
| Invalid ZIP | `Invalid CDR ZIP: {details}` | CDR does not decode to a valid ZIP file, or the ZIP contains no XML. |
| Invalid XML | `Invalid CDR XML: {details}` | XML file inside the CDR ZIP is malformed. |

#### REST API Errors (Dispatch Guides)

| Error | Message Pattern | Cause |
|-------|----------------|-------|
| REST credentials missing | `SUNAT REST credentials (SUNAT_REST_CLIENT_ID / SUNAT_REST_KEY) not configured` | Server configuration is missing the SUNAT REST API credentials needed for dispatch guides. |
| Token URL missing | `SUNAT_REST_TOKEN_URL not configured` | Server configuration is missing the SUNAT OAuth2 token URL. |
| Token request failed | `SUNAT token request failed: HTTP {status_code}` | Failed to obtain OAuth2 token from SUNAT. |
| Token incomplete | `SUNAT token response missing access_token` | SUNAT token endpoint responded 200 but did not include `access_token`. |
| REST API URL missing | `SUNAT_REST_API_URL not configured` | Server configuration is missing the SUNAT GRE REST API URL. |
| Guide submission failed | `SUNAT REST sendGRE failed: HTTP {status_code} - {response_text}` | SUNAT REST API rejected the dispatch guide submission. |
| Missing ticket number | `SUNAT REST sendGRE response missing numTicket: {body}` | SUNAT accepted the guide but did not return a ticket number for tracking. |
| Ticket query failed | `SUNAT REST ticket query failed: HTTP {status_code}` | Failed to check the processing status of a dispatch guide ticket. |

---

## 7. Internal Errors

These indicate issues within the billing service itself.

### HTTP 500 - Internal Server Error

| Error | Message Pattern | Cause |
|-------|----------------|-------|
| XML build failure | `Failed to build XML: {details}` | Error generating the UBL 2.1 XML for an invoice or receipt. Likely caused by invalid or missing data that passed validation. |
| XML build failure (GR) | `Failed to build GR XML: {details}` | Same as above, for dispatch guides. |
| XML signing failure | `Failed to sign XML: {details}` | Error signing the XML with the client's digital certificate. The certificate may be corrupted, expired, or the password may be incorrect. |
| XML signing failure (GR) | `Failed to sign GR XML: {details}` | Same as above, for dispatch guides. |
| Generic billing error | `{error message}` | Catch-all for unexpected errors in the billing flow. |

---

## 8. Document Status Flow

Documents progress through these statuses:

```
CREATED → SIGNED → SENT → ACCEPTED
                       ↘ REJECTED
                       ↘ ERROR
```

| Status | Description | Retryable? |
|--------|-------------|-----------|
| `CREATED` | Document saved to database | No |
| `SIGNED` | XML built and signed successfully | Yes |
| `SENT` | Submitted to SUNAT, awaiting confirmation | No |
| `ACCEPTED` | SUNAT accepted the document | No |
| `REJECTED` | SUNAT rejected the document (check `cdr_code` and `cdr_description` for details) | Yes |
| `ERROR` | Submission failed (network error, SUNAT unavailable, etc.) | Yes |

When a document is `REJECTED`, the `cdr_code` and `cdr_description` fields in the detail response contain the specific SUNAT error code and message.

---

## Quick Reference: HTTP Status Summary

| HTTP Status | Meaning | When |
|-------------|---------|------|
| **401** | Unauthorized | Invalid or inactive API key |
| **403** | Forbidden | IP not authorized |
| **400** | Bad Request | Invalid operation (wrong certificate format, invalid retry) |
| **404** | Not Found | Document or guide does not exist |
| **409** | Conflict | Duplicate resource (RUC already registered) |
| **422** | Unprocessable Entity | Validation error (missing fields, invalid values, missing configuration) |
| **500** | Internal Server Error | XML build/sign failure, unexpected billing error |
| **502** | Bad Gateway | SUNAT communication failure (SOAP, REST, CDR parsing) |
