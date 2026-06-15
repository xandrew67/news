# ── Builder stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM python:3.11-slim

LABEL maintainer="xandrew67"
LABEL description="Australian News Intelligence Agent"

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY agents/ ./agents/
COPY config/ ./config/
COPY main.py .

# Create output directory
RUN mkdir -p output

# Non-root user for security
RUN useradd -m -u 1000 agentuser && chown -R agentuser:agentuser /app
USER agentuser

# Health check — confirms Python can import the main module
HEALTHCHECK --interval=60s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "from agents.orchestrator import Orchestrator; print('ok')"

ENTRYPOINT ["python", "main.py"]
CMD ["--loop"]
