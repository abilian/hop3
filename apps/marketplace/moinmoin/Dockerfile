FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Download and install MoinMoin
ENV MOIN_VERSION=2.0.0b1
RUN curl -L "https://github.com/moinwiki/moin/releases/download/${MOIN_VERSION}/moin-${MOIN_VERSION}.tar.gz" | tar xz --strip-components=1

# Install Python dependencies
RUN pip install --no-cache-dir gunicorn && \
    pip install --no-cache-dir -e .

# Copy startup script
COPY start.py /app/start.py
RUN chmod +x /app/start.py

EXPOSE 8080

CMD ["python3", "/app/start.py"]
