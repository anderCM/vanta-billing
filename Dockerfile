FROM python:3.12-slim AS base

WORKDIR /src
ENV PYTHONPATH=/src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Development ---
FROM base AS dev

COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]

# --- Production ---
FROM base AS prod

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --create-home appuser

COPY --chown=appuser:appuser . .

USER appuser
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
