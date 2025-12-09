# Demo 22: Radicale - CalDAV/CardDAV Server
# A simple calendar and contact server

FROM python:3.12-slim

WORKDIR /app

# renovate: datasource=pypi depName=radicale
ARG RADICALE_VERSION=3.5.9

# Install radicale and dependencies
RUN pip install --no-cache-dir radicale==${RADICALE_VERSION} passlib[bcrypt]

# Create data directory
RUN mkdir -p /app/data/collections

# Copy configuration and startup script
COPY config.template /app/config.template
COPY rights /app/rights
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Radicale runs on port 5232
EXPOSE 5232

CMD ["/app/start.sh"]
