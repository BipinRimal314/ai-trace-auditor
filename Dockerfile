FROM python:3.11-slim

WORKDIR /app

# WeasyPrint runtime deps + git for repo ingestion clone.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libffi8 \
        shared-mime-info \
        fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY requirements/ ./requirements/
COPY tests/fixtures/ ./tests/fixtures/

RUN pip install --no-cache-dir -e ".[web,pdf]"

RUN mkdir -p /tmp/aitrace
ENV REPO_TMPDIR=/tmp/aitrace
ENV PDF_TMPDIR=/tmp/aitrace
ENV MAX_REPO_BYTES=52428800
ENV REPO_FETCH_TIMEOUT=30

EXPOSE 8001

CMD ["python", "-m", "ai_trace_auditor.web.server"]
