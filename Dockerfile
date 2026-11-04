FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SHALAEMES_DATA_DIR=/data \
    PORT=8080

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system app \
    && adduser --system --ingroup app app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app
COPY run_server.py ./
COPY entrypoint.sh ./

RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /data \
    && chown -R app:app /app /data

EXPOSE 8080
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request,sys; p=os.getenv('PORT','8080'); sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+p+'/health', timeout=3).getcode()==200 else 1)"

ENTRYPOINT ["/app/entrypoint.sh"]
