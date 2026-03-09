"""Shared correlative management and transaction helpers.

Used by billing.py and gr_billing.py to avoid duplicating correlative logic
and to ensure correlativos are not wasted on pre-SUNAT failures.
"""

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.sunat_catalogs import DocumentStatus

logger = logging.getLogger(__name__)


def next_correlative(db: Session, client_id: str, document_type: str, series: str) -> int:
    """Atomically reserve the next correlative for a given client/type/series.

    This runs within the current transaction — if the transaction is rolled back,
    the correlative increment is also undone.
    """
    result = db.execute(
        text(
            """
            INSERT INTO document_series (client_id, document_type, series, current_correlative)
            VALUES (:client_id, :doc_type, :series, 1)
            ON CONFLICT ON CONSTRAINT uq_client_doc_type_series
            DO UPDATE SET current_correlative = document_series.current_correlative + 1
            RETURNING current_correlative
            """
        ),
        {"client_id": client_id, "doc_type": document_type, "series": series},
    )
    return result.scalar_one()


def rollback_on_pre_sunat_error(db: Session) -> None:
    """Rollback the current transaction on pre-SUNAT failures (XML build/sign).

    This undoes the correlative increment and any persisted document/items,
    so no correlativo is wasted when the document never reached SUNAT.
    """
    logger.info("Rolling back transaction — correlative not consumed")
    db.rollback()


def set_error_status(db: Session, record) -> None:
    """Mark a document or dispatch guide as ERROR and commit.

    Used only after SUNAT send failures — the document has signed XML
    and is preserved for retry via the retry endpoint (no new correlative needed).
    """
    record.status = DocumentStatus.ERROR
    db.commit()
