from sqlalchemy.orm import Session

from app.models.dispatch_guide import DispatchGuide
from app.models.document_series import DocumentSeries


def get_dispatch_guide_by_id(
    db: Session, client_id: str, guide_id: str
) -> DispatchGuide | None:
    return (
        db.query(DispatchGuide)
        .filter(
            DispatchGuide.id == guide_id,
            DispatchGuide.client_id == client_id,
        )
        .first()
    )


def list_dispatch_guides(
    db: Session,
    client_id: str,
    *,
    document_type: str | None = None,
    status: str | None = None,
    date_from=None,
    date_to=None,
    page: int = 1,
    page_size: int = 20,
) -> list[DispatchGuide]:
    query = db.query(DispatchGuide).filter(DispatchGuide.client_id == client_id)

    if document_type:
        query = query.filter(DispatchGuide.document_type == document_type)
    if status:
        query = query.filter(DispatchGuide.status == status)
    if date_from:
        query = query.filter(DispatchGuide.issue_date >= date_from)
    if date_to:
        query = query.filter(DispatchGuide.issue_date <= date_to)

    query = query.order_by(DispatchGuide.created_at.desc())
    offset = (page - 1) * page_size
    return query.offset(offset).limit(page_size).all()


def get_next_correlative(
    db: Session, client_id: str, document_type: str, series: str
) -> int:
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
