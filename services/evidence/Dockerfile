FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY packages/artae-labs-client/ /build/artae-labs-client/
COPY services/evidence/ /app/
RUN python -m pip install --no-cache-dir /build/artae-labs-client . \
    && useradd --create-home --uid 10002 evidence

USER evidence
CMD ["video-intelligence-evidence-worker"]
