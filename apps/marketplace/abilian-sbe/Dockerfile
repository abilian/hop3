FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Download Abilian SBE
RUN curl -L "https://github.com/abilian/abilian-sbe-monorepo/archive/refs/heads/main.tar.gz" | tar xz --strip-components=1

# Install dependencies
ENV PATH="/root/.local/bin:$PATH"
RUN uv sync

# Copy startup script
COPY start.py /app/start.py
RUN chmod +x /app/start.py

EXPOSE 8000

CMD ["python3", "/app/start.py"]
