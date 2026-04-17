FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    netcat-traditional \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir psycopg2-binary

# Create non-root user
RUN useradd -m -u 1000 appuser

# Copy application code
COPY . .

# Make start script executable
RUN chmod +x /app/scripts/start.sh

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Create directory for temporary files with proper permissions
RUN mkdir -p /app/temp && \
    chown -R appuser:appuser /app/temp && \
    chmod 755 /app/temp

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 10000

# Run migrations and start server (branches on ENVIRONMENT in start.sh)
CMD ["/app/scripts/start.sh"]
