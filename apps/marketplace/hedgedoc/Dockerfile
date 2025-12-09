# Demo 21: HedgeDoc
# Collaborative markdown editor

FROM node:20-alpine

WORKDIR /app

# Install dependencies
RUN apk add --no-cache curl jq python3

# renovate: datasource=github-releases depName=hedgedoc/hedgedoc
ARG HEDGEDOC_VERSION=1.10.3

# Download and extract HedgeDoc
RUN curl -L https://github.com/hedgedoc/hedgedoc/releases/download/${HEDGEDOC_VERSION}/hedgedoc-${HEDGEDOC_VERSION}.tar.gz | tar -xz --strip-components 1

# Install dependencies (yarn is already in node:20-alpine)
RUN yarn config set --home enableTelemetry 0 && \
    yarn install --immutable

# Create directories
RUN mkdir -p /app/uploads /app/tmp

# Set production mode
ENV NODE_ENV=production

# Expose port
EXPOSE 3000

# Start script
COPY start.py /app/start.py

CMD ["python3", "/app/start.py"]
