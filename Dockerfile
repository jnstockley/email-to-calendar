FROM python:3.13.7-alpine

ARG VERSION=0.0.0.dev

RUN apk upgrade --no-cache && \
    apk add build-base protobuf-dev pkgconfig --no-cache   && \
    adduser -S app && \
    mkdir /app && \
    chown app /app
USER app

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY . /app

RUN sed -i "s/^version = .*/version = \"${VERSION}\"/" /app/pyproject.toml

RUN uv sync --frozen --no-cache --no-dev

ENV PATH=/app/.venv/bin:$PATH
ENV PYTHONPATH=src

ENTRYPOINT ["uv", "run", "--directory", "src", "main.py"]
