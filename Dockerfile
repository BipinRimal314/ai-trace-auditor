FROM python:3.11-slim

WORKDIR /app

# WeasyPrint runtime dependencies (libpango + libharfbuzz pull in cairo,
# gdk-pixbuf, fontconfig). fonts-dejavu provides a sane default font fallback.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
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

EXPOSE 8001

CMD ["python", "-m", "ai_trace_auditor.web.server"]
