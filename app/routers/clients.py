from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_client
from app.exceptions import BillingError
from app.models.client import Client
from app.schemas.client import ClientCreate, ClientCreateResponse, ClientRead, ClientUpdate
from app.services.client_service import (
    register_client,
    rotate_client_api_key,
    update_client,
    upload_client_certificate,
)

router = APIRouter(prefix="/clients", tags=["clients"])


@router.post("", response_model=ClientCreateResponse, status_code=status.HTTP_201_CREATED)
def create_client(data: ClientCreate, db: Session = Depends(get_db)):
    try:
        client, api_key = register_client(
            db,
            ruc=data.ruc,
            razon_social=data.razon_social,
            nombre_comercial=data.nombre_comercial,
            direccion=data.direccion,
            ubigeo=data.ubigeo,
            sol_user=data.sol_user,
            sol_password=data.sol_password,
        )
    except BillingError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return ClientCreateResponse(
        client_id=client.id,
        api_key=api_key,
        ruc=client.ruc,
        razon_social=client.razon_social,
    )


@router.get("/me", response_model=ClientRead)
def get_me(client: Client = Depends(get_current_client)):
    return client


@router.put("/me", response_model=ClientRead)
def update_me(
    data: ClientUpdate,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    fields = data.model_dump(exclude_unset=True)
    client = update_client(db, client, **fields)
    return client


@router.post("/me/rotate-key")
def rotate_key(
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    new_api_key = rotate_client_api_key(db, client)
    return {
        "api_key": new_api_key,
        "message": "Save the new API key — it will not be shown again. The previous key is now invalid.",
    }


@router.post("/me/certificate", status_code=status.HTTP_200_OK)
def upload_certificate(
    file: UploadFile,
    password: str,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith((".pfx", ".p12")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a .pfx or .p12 certificate",
        )

    pfx_data = file.file.read()
    upload_client_certificate(db, client, pfx_data, password)
    return {"message": "Certificate uploaded successfully"}
