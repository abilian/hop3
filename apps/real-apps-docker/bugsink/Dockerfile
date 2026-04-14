# Bugsink Dockerfile for Hop3
# Built from debian:trixie-slim + python + pip install bugsink

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    libpq5 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash bugsink

WORKDIR /opt/bugsink

ARG BUGSINK_VERSION=2.1.2
RUN python3 -m venv /opt/bugsink/venv \
    && /opt/bugsink/venv/bin/pip install --no-cache-dir \
        "bugsink==${BUGSINK_VERSION}" \
        "gunicorn>=21.0" \
        "psycopg2-binary>=2.9"

ENV PATH="/opt/bugsink/venv/bin:${PATH}"

RUN mkdir -p /data && chown -R bugsink:bugsink /data /opt/bugsink

COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
