FROM ghcr.io/astral-sh/uv:python3.11-alpine

RUN apk add --no-cache bash git curl openssh-client ca-certificates

WORKDIR /app

COPY scripts /app/scripts

RUN uv pip install --system pyyaml jsonschema

ENTRYPOINT ["python3", "/app/scripts/promoter/promote.py"]
