# Demo 40: Ghost Blogging Platform
# Modern publishing platform for professional bloggers
# https://ghost.org/

FROM ghost:5-alpine

# Copy startup script to parse DATABASE_URL
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Ghost default port
EXPOSE 2368

# Use our startup script
ENTRYPOINT ["/usr/local/bin/start.sh"]
