"""SUNAT SOAP integration — public API.

Usage:
    from app.services.integrations.sunat import send_document, query_document_status
"""

from .soap_sender import send_document
from .soap_status import query_document_status

__all__ = ["send_document", "query_document_status"]
