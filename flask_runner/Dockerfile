FROM python:3.11-slim

# git needed by some pip packages; curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /runner

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY runner.py .

# Non-root user — student code runs as this user
RUN useradd -m -u 1001 runner
USER runner

EXPOSE 6000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s \
    CMD curl -f http://localhost:6000/health || exit 1

CMD ["python", "runner.py"]
