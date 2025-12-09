FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    libpq-dev \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Download AIPress24
RUN curl -L "https://github.com/aipress24/aipress24/archive/refs/heads/main.tar.gz" | tar xz --strip-components=1

# Install dependencies and build
RUN uv sync --no-dev && \
    .venv/bin/flask vite install && \
    .venv/bin/flask vite build

# Copy startup script
COPY start.py /app/start.py
RUN chmod +x /app/start.py

EXPOSE 8000

CMD ["python3", "/app/start.py"]
