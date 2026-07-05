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

USER xenalgo

CMD ["python", "-m", "xenalgo", "--profile", "live"]
