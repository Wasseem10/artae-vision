FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY services/alerts /app/services/alerts
RUN pip install --no-cache-dir /app/services/alerts \
    && useradd --create-home --uid 10003 alerts

USER alerts
CMD ["video-intelligence-alert-worker"]
