from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_client
from app.exceptions import BillingError, MissingCredentialsError, SUNATError
from app.models.client import Client
from app.schemas.dispatch_guide import (
    DispatchGuideDetail,
    DispatchGuideRead,
    GRRCreate,
    GRTCreate,
)
from app.services.dispatch_guide_service import (
    get_dispatch_guide_by_id,
    list_dispatch_guides,
)
from app.services.gr_billing import (
    check_dispatch_guide_status,
    create_and_send_dispatch_guide,
    retry_send_dispatch_guide,
)
from app.services.sunat_catalogs import GR_SERIES_PREFIXES

router = APIRouter(tags=["dispatch-guides"])

_DEFAULT_SERIES = {
    "09": "T001",
    "31": "V001",
}


@router.post(
    "/dispatch-guides/remitente",
    response_model=DispatchGuideDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_grr(
    data: GRRCreate,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return await _create_dispatch_guide(db, client, "09", data)


@router.post(
    "/dispatch-guides/transportista",
    response_model=DispatchGuideDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_grt(
    data: GRTCreate,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return await _create_dispatch_guide(db, client, "31", data)


@router.get("/dispatch-guides", response_model=list[DispatchGuideRead])
def get_dispatch_guides(
    document_type: str | None = Query(None, max_length=2),
    document_status: str | None = Query(None, alias="status"),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return list_dispatch_guides(
        db,
        client.id,
        document_type=document_type,
        status=document_status,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


@router.get("/dispatch-guides/{guide_id}", response_model=DispatchGuideDetail)
def get_dispatch_guide(
    guide_id: str,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return _get_or_404(db, client, guide_id)


@router.post("/dispatch-guides/{guide_id}/retry", response_model=DispatchGuideRead)
async def retry_dispatch_guide(
    guide_id: str,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    guide = _get_or_404(db, client, guide_id)
    try:
        return await retry_send_dispatch_guide(db, client, guide)
    except MissingCredentialsError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    except SUNATError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except BillingError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/dispatch-guides/{guide_id}/status", response_model=DispatchGuideRead)
async def query_dispatch_guide_status(
    guide_id: str,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    guide = _get_or_404(db, client, guide_id)
    try:
        return await check_dispatch_guide_status(db, client, guide)
    except MissingCredentialsError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    except SUNATError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


async def _create_dispatch_guide(db, client, document_type, data):
    if not data.series:
        if document_type == "09":
            data.series = client.serie_grr
        elif document_type == "31":
            data.series = client.serie_grt
        if not data.series:
            data.series = _DEFAULT_SERIES[document_type]

    # Validate series prefix matches document type
    expected_prefix = GR_SERIES_PREFIXES[document_type]
    if not data.series.startswith(expected_prefix):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Series for document type {document_type} must start with '{expected_prefix}'",
        )

    try:
        guide = await create_and_send_dispatch_guide(
            db, client, document_type=document_type, data=data
        )
    except MissingCredentialsError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    except SUNATError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except BillingError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )

    return guide


def _get_or_404(db, client, guide_id):
    guide = get_dispatch_guide_by_id(db, client.id, guide_id)
    if not guide:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dispatch guide not found",
        )
    return guide
