"""SUNAT catalog code mappings.

Translates user-friendly values to SUNAT catalog codes.
"""

from enum import Enum


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
