"""SUNAT catalog code mappings.

Translates user-friendly values to SUNAT catalog codes.
"""

from datetime import datetime, timedelta, timezone
from enum import Enum

# --- Peru timezone (UTC-5) ---

PERU_TZ = timezone(timedelta(hours=-5))


def peru_now() -> datetime:
    """Return the current datetime in Peru timezone."""
    return datetime.now(PERU_TZ)


def peru_issue_date() -> str:
    """Return today's date in Peru timezone as YYYY-MM-DD string."""
    return peru_now().strftime("%Y-%m-%d")


# --- Document status lifecycle ---

class DocumentStatus(str, Enum):
    CREATED = "CREATED"
    SIGNED = "SIGNED"
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


# --- IGV affectation prefixes (Catálogo 07 groups) ---

class IGVGroup(str, Enum):
    GRAVADO = "1"      # 10-17
    EXONERADO = "2"    # 20-21
    INAFECTO = "3"     # 30-36


# --- Catálogo 03 - Unit codes ---

ITEM_TYPE_TO_UNIT_CODE = {
    "product": "NIU",
    "service": "ZZ",
}

# --- Catálogo 07 - IGV affectation types ---

TAX_TYPE_TO_IGV_CODE = {
    "gravado": "10",
    "exonerado": "20",
    "inafecto": "30",
}

# --- Catálogo 06 - Document identity types ---

CUSTOMER_DOC_TYPE_TO_CODE = {
    "ruc": "6",
    "dni": "1",
}

# --- Catálogo 18 - Transport modality ---

TRANSPORT_MODALITY_CODES = {
    "public": "01",    # Transporte público
    "private": "02",   # Transporte privado
}

# --- Catálogo 20 - Transfer reason codes ---

TRANSFER_REASON_CODES = {
    "venta": "01",
    "compra": "02",
    "traslado_entre_establecimientos": "04",
    "importacion": "08",
    "exportacion": "09",
    "otros": "13",
}

# --- Guía de Remisión document types ---

GR_DOCUMENT_TYPES = {
    "grr": "09",  # Guía de Remisión Remitente
    "grt": "31",  # Guía de Remisión Transportista
}

GR_SERIES_PREFIXES = {
    "09": "T",
    "31": "V",
}

# --- Catálogo 09 - Credit note reason codes ---

CREDIT_NOTE_REASON_CODES = {
    "anulacion_de_la_operacion": "01",
    "anulacion_por_error_en_el_ruc": "02",
    "correccion_por_error_en_la_descripcion": "03",
    "descuento_global": "04",
    "descuento_por_item": "05",
    "devolucion_total": "06",
    "devolucion_por_item": "07",
    "bonificacion": "08",
    "disminucion_en_el_valor": "09",
    "otros_conceptos": "10",
    "ajustes_de_operaciones_de_exportacion": "11",
    "ajustes_afectos_al_ivap": "12",
    "correccion_del_monto_neto_pendiente_de_pago": "13",
}
