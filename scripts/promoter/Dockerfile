FROM python:3.11-alpine

RUN apk add --no-cache git curl

WORKDIR /app

COPY scripts/promoter/promote.py /app/promote.py

RUN pip install --no-cache-dir pyyaml jsonschema

ENTRYPOINT ["python3", "/app/promote.py"]
