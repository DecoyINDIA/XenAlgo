FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV XENALGO_PROFILE=live

WORKDIR /app

RUN addgroup --system xenalgo && adduser --system --ingroup xenalgo xenalgo

COPY requirements.lock requirements.lock
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.lock

COPY . .

RUN mkdir -p /app/Diary/state /app/Diary/logs /app/Supply/database /app/.xenalgo-secrets \
    && chown -R xenalgo:xenalgo /app/Diary /app/Supply /app/.xenalgo-secrets

USER xenalgo

CMD ["python", "-m", "xenalgo", "--profile", "live"]
