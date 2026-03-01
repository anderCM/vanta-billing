from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_series import DocumentSeries


def get_document_by_id(db: Session, client_id: str, document_id: str) -> Document | None:
    return (
        db.query(Document)
        .filter(Document.id == document_id, Document.client_id == client_id)
        .first()
    )


def list_documents(
    db: Session,
    client_id: str,
    *,
    document_type: str | None = None,
    status: str | None = None,
    date_from=None,
    date_to=None,
    page: int = 1,
    page_size: int = 20,
) -> list[Document]:
    query = db.query(Document).filter(Document.client_id == client_id)

    if document_type:
        query = query.filter(Document.document_type == document_type)
    if status:
        query = query.filter(Document.status == status)
    if date_from:
        query = query.filter(Document.issue_date >= date_from)
    if date_to:
        query = query.filter(Document.issue_date <= date_to)

    query = query.order_by(Document.created_at.desc())
    offset = (page - 1) * page_size
    return query.offset(offset).limit(page_size).all()


def get_next_correlative(
    db: Session, client_id: str, document_type: str, series: str
) -> int:
    """Return the next correlative that will be used for a given series."""
    ds = (
        db.query(DocumentSeries)
        .filter(
            DocumentSeries.client_id == client_id,
            DocumentSeries.document_type == document_type,
            DocumentSeries.series == series,
        )
        .first()
    )
    return (ds.current_correlative + 1) if ds else 1
