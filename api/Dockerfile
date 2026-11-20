FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app/api
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY reconlens ./reconlens
RUN uv sync --frozen --no-dev
ENV PATH="/app/api/.venv/bin:$PATH"
# Seed one-shot: same image, `python -m reconlens.seed` with ./data mounted at /app/data (or CATALOG_CSV set).
EXPOSE 8000
CMD ["uvicorn", "reconlens.main:app", "--host", "0.0.0.0", "--port", "8000"]
