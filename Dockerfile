# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Pillow / system deps + locales
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential libpq-dev libjpeg-dev zlib1g-dev \
       tzdata \
       postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first for better layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn  # already in requirements; ensures presence

COPY . /app
RUN rm -rf /app/media /app.db.sqlite3 /app/db.sqlite3 /app/__pycache__ /app/osts/__pycache__

# collectstatic moved to entrypoint so STATIC_ROOT is populated at runtime
RUN useradd -m -r osts && chown -R osts:osts /app
USER osts

EXPOSE 8000
ENV OSTS_ENV=prod DJANGO_SETTINGS_MODULE=osts.settings

CMD ["bash", "-c", "python manage.py collectstatic --noinput && \
    python manage.py migrate --noinput && \
    gunicorn osts.wsgi:application -b 0.0.0.0:8000 -w 4 -k gthread --threads 2 --timeout 30 --access-logfile - --error-logfile -"]