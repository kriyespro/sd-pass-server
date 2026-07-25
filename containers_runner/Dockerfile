FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /runner

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY runner.py .

EXPOSE 6100

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s \
    CMD curl -f http://localhost:6100/health || exit 1

CMD ["python", "runner.py"]
