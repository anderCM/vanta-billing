from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_client
from app.exceptions import BillingError, MissingCredentialsError, SUNATError
from app.models.client import Client
from app.schemas.document import (
    DocumentDetail,
    DocumentRead,
    InvoiceCreate,
    ReceiptCreate,
)
from app.services.billing import check_document_status, create_and_send_document, retry_send_document
from app.services.document_service import get_document_by_id, list_documents
from app.services.sunat_catalogs import DocumentStatus

router = APIRouter(tags=["documents"])


@router.post("/invoices", response_model=DocumentDetail, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    data: InvoiceCreate,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return await _create_document(db, client, "01", data)


@router.post("/receipts", response_model=DocumentDetail, status_code=status.HTTP_201_CREATED)
async def create_receipt(
    data: ReceiptCreate,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return await _create_document(db, client, "03", data)


@router.get("/documents", response_model=list[DocumentRead])
def get_documents(
    document_type: str | None = Query(None, max_length=2),
    document_status: str | None = Query(None, alias="status"),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return list_documents(
        db,
        client.id,
        document_type=document_type,
        status=document_status,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: str,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return _get_or_404(db, client, document_id)


@router.post("/documents/{document_id}/retry", response_model=DocumentRead)
async def retry_document(
    document_id: str,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    document = _get_or_404(db, client, document_id)
    try:
        return await retry_send_document(db, client, document)
    except MissingCredentialsError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except SUNATError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except BillingError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/documents/{document_id}/status", response_model=DocumentRead)
async def query_document_status(
    document_id: str,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    document = _get_or_404(db, client, document_id)
    try:
        return await check_document_status(db, client, document)
    except MissingCredentialsError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except SUNATError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


async def _create_document(
    db: Session,
    client: Client,
    document_type: str,
    data: InvoiceCreate | ReceiptCreate,
):
    # Resolve series from client config if not provided
    if not data.series:
        if document_type == "01":
            data.series = client.serie_factura
        elif document_type == "03":
            data.series = client.serie_boleta
        if not data.series:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No series provided and client has no default series configured",
            )

    try:
        document = await create_and_send_document(db, client, document_type=document_type, data=data)
    except MissingCredentialsError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except BillingError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    if document.status == DocumentStatus.ERROR:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=jsonable_encoder(DocumentDetail.model_validate(document)),
        )
    return document


def _get_or_404(db: Session, client: Client, document_id: str):
    document = get_document_by_id(db, client.id, document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document
