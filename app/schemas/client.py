from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ClientCreate(BaseModel):
    ruc: str = Field(..., min_length=11, max_length=11)
    razon_social: str = Field(..., max_length=255)
    nombre_comercial: str | None = None
    direccion: str | None = None
    ubigeo: str | None = Field(None, max_length=6)
    sol_user: str | None = None
    sol_password: str | None = None


class ClientCreateResponse(BaseModel):
    client_id: str
    api_key: str
    ruc: str
    razon_social: str
    message: str = "Save the api_key — it will not be shown again."


class ClientRead(BaseModel):
    client_id: str
    ruc: str
    razon_social: str
    nombre_comercial: str | None
    direccion: str | None
    ubigeo: str | None
    has_sol_credentials: bool
    has_certificate: bool
    serie_factura: str | None
    serie_boleta: str | None
    serie_grr: str | None
    serie_grt: str | None
    send_email: bool
    generate_pdf: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def compute_fields(cls, data):
        if hasattr(data, "id"):
            # ORM model object
            return {
                "client_id": data.id,
                "ruc": data.ruc,
                "razon_social": data.razon_social,
                "nombre_comercial": data.nombre_comercial,
                "direccion": data.direccion,
                "ubigeo": data.ubigeo,
                "has_sol_credentials": bool(data.sol_user and data.sol_password),
                "has_certificate": bool(data.certificate),
                "serie_factura": data.serie_factura,
                "serie_boleta": data.serie_boleta,
                "serie_grr": data.serie_grr,
                "serie_grt": data.serie_grt,
                "send_email": data.send_email,
                "generate_pdf": data.generate_pdf,
                "is_active": data.is_active,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
            }
        return data


class ClientUpdate(BaseModel):
    razon_social: str | None = None
    nombre_comercial: str | None = None
    direccion: str | None = None
    ubigeo: str | None = None
    sol_user: str | None = None
    sol_password: str | None = None
    serie_factura: str | None = Field(None, max_length=4)
    serie_boleta: str | None = Field(None, max_length=4)
    serie_grr: str | None = Field(None, max_length=4)
    serie_grt: str | None = Field(None, max_length=4)
    send_email: bool | None = None
    generate_pdf: bool | None = None
