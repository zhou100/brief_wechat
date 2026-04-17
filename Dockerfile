FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    netcat-traditional \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir psycopg2-binary

RUN useradd -m -u 1000 appuser

COPY backend/ .
RUN chmod +x /app/scripts/start.sh

ENV PYTHONUNBUFFERED=1

RUN mkdir -p /app/temp && \
    chown -R appuser:appuser /app/temp && \
    chmod 755 /app/temp

USER appuser

EXPOSE 10000

CMD ["/app/scripts/start.sh"]
