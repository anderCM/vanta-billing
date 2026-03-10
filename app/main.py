import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.exceptions import (
    BillingError,
    CDRParseError,
    MissingCredentialsError,
    SUNATError,
    XMLBuildError,
    XMLSignError,
)
from app.middleware.ip_whitelist import IPWhitelistMiddleware
from app.routers import clients, credit_notes, dispatch_guides, documents

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("Application started")
    yield
    logger.info("Application shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
)

# Middleware
app.add_middleware(IPWhitelistMiddleware)

# Routers
API_PREFIX = "/api/v1"
app.include_router(clients.router, prefix=API_PREFIX)
app.include_router(documents.router, prefix=API_PREFIX)
app.include_router(credit_notes.router, prefix=API_PREFIX)
app.include_router(dispatch_guides.router, prefix=API_PREFIX)


# Exception handlers
@app.exception_handler(MissingCredentialsError)
async def missing_credentials_handler(request: Request, exc: MissingCredentialsError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(XMLBuildError)
async def xml_build_handler(request: Request, exc: XMLBuildError):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.exception_handler(XMLSignError)
async def xml_sign_handler(request: Request, exc: XMLSignError):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.exception_handler(CDRParseError)
async def cdr_parse_handler(request: Request, exc: CDRParseError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(SUNATError)
async def sunat_handler(request: Request, exc: SUNATError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(BillingError)
async def billing_handler(request: Request, exc: BillingError):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/health")
def health():
    return {"status": "ok"}
