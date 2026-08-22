FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY services/api/ /app/
RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 api \
    && mkdir -p /data/evidence \
    && chown -R api:api /app /data/evidence

USER api
EXPOSE 8000

CMD ["sh", "-c", "alembic -c /app/alembic.ini upgrade head && video-intelligence-api"]
