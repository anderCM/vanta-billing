from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_client
from app.exceptions import BillingError, MissingCredentialsError, SUNATError
from app.models.client import Client
from app.models.document import Document
from app.schemas.credit_note import CreditNoteCreate, CreditNoteDetail, CreditNoteRead
from app.services.cn_billing import (
    DOCUMENT_TYPE_CREDIT_NOTE,
    create_and_send_credit_note,
    retry_send_credit_note,
)
from app.services.sunat_catalogs import DocumentStatus

router = APIRouter(tags=["credit-notes"])


@router.post("/credit-notes", response_model=CreditNoteDetail, status_code=status.HTTP_201_CREATED)
async def create_credit_note(
    data: CreditNoteCreate,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    # Resolve series from client config if not provided
    if not data.series:
        ref_doc = db.query(Document).filter(
            Document.id == data.reference_document_id,
            Document.client_id == client.id,
        ).first()
        if ref_doc and ref_doc.document_type == "01":
            data.series = client.serie_nota_credito_factura
        elif ref_doc and ref_doc.document_type == "03":
            data.series = client.serie_nota_credito_boleta
        if not data.series:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No series provided and client has no default credit note series configured",
            )

    try:
        document = await create_and_send_credit_note(db, client, data=data)
    except MissingCredentialsError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except BillingError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    if document.status == DocumentStatus.ERROR:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=jsonable_encoder(CreditNoteDetail.model_validate(document)),
        )
    return document


@router.get("/credit-notes", response_model=list[CreditNoteRead])
def list_credit_notes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    offset = (page - 1) * page_size
    return (
        db.query(Document)
        .filter(
            Document.client_id == client.id,
            Document.document_type == DOCUMENT_TYPE_CREDIT_NOTE,
        )
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )


@router.get("/credit-notes/{credit_note_id}", response_model=CreditNoteDetail)
def get_credit_note(
    credit_note_id: str,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return _get_or_404(db, client, credit_note_id)


@router.post("/credit-notes/{credit_note_id}/retry", response_model=CreditNoteRead)
async def retry_credit_note(
    credit_note_id: str,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    document = _get_or_404(db, client, credit_note_id)
    try:
        return await retry_send_credit_note(db, client, document)
    except MissingCredentialsError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except SUNATError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except BillingError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _get_or_404(db: Session, client: Client, credit_note_id: str) -> Document:
    document = (
        db.query(Document)
        .filter(
            Document.id == credit_note_id,
            Document.client_id == client.id,
            Document.document_type == DOCUMENT_TYPE_CREDIT_NOTE,
        )
        .first()
    )
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credit note not found")
    return document
