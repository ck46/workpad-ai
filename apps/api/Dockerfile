FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      pandoc \
      libpango-1.0-0 \
      libpangoft2-1.0-0 \
      libharfbuzz0b \
      libcairo2 \
      libgdk-pixbuf-2.0-0 \
      libffi8 \
      fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY uv.lock ./
RUN uv sync --frozen --no-dev

COPY src ./src

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

