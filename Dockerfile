FROM python:3.13.7 AS  build

ARG VERSION=0.0.0.dev

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY ./pyproject.toml .
COPY ./uv.lock .

RUN uv version ${VERSION} && \
    uv sync --frozen --no-cache --no-dev

FROM python:3.13.7-slim

RUN adduser app

USER app

WORKDIR /app

COPY . .
COPY --from=build /app/.venv .venv
COPY --from=build /app/pyproject.toml .
COPY --from=build /app/uv.lock .

# Set up environment variables for production
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/src/:$PYTHONPATH

ENTRYPOINT ["python", "src/main.py"]
