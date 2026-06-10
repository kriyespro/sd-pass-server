FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=core.settings.dev

WORKDIR /app

# postgresql-client-16 must match postgres:16 in docker-compose (pg_dump version check).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg libpq5 \
    && install -d /usr/share/keyrings \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt package.json ./
RUN pip install --no-cache-dir -r requirements.txt

# Install Node + build Tailwind CSS
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN npm ci --omit=dev && npm run build:css && rm -rf node_modules

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
