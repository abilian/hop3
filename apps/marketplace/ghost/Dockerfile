FROM ghost:5-alpine

# Copy config file
COPY config.production.json /var/lib/ghost/config.production.json

# Set permissions
RUN chown node:node /var/lib/ghost/config.production.json
