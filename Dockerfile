FROM dhi.io/python:3.14.2-dev AS  build

ARG VERSION=0.0.0.dev

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/src/:$PYTHONPATH

WORKDIR /app

COPY --from=dhi.io/uv:0 /uv /uvx /bin/

COPY ./pyproject.toml .
COPY ./uv.lock .

RUN uv version ${VERSION} && \
    uv sync --frozen --no-cache --no-dev

FROM dhi.io/python:3.14.2

# Set up environment variables for production
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/src/:$PYTHONPATH

WORKDIR /app

COPY . .
COPY --from=build /app/.venv .venv
COPY --from=build /app/pyproject.toml .
COPY --from=build /app/uv.lock .

HEALTHCHECK --interval=60s --timeout=10s --start-period=10s --retries=3 \
    CMD ["python", "src/main.py", "healthcheck"]

ENTRYPOINT ["python", "src/main.py"]
