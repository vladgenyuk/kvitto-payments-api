FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .
COPY scripts ./scripts
RUN useradd --uid 10001 --create-home kvitto && mkdir /data && chown kvitto:kvitto /data
USER kvitto
ENV DATABASE_URL=sqlite+aiosqlite:////data/kvitto.db
EXPOSE 8000
CMD ["uvicorn", "app.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS test
USER root
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY pyproject.toml .
COPY tests ./tests
USER kvitto
ENV COVERAGE_FILE=/tmp/.coverage
CMD ["sh", "-c", "ruff check --no-cache . && ruff format --check --no-cache . && coverage run --branch --source=app -m pytest -q -W error -p no:cacheprovider && coverage report --fail-under=95"]

FROM base AS runtime
