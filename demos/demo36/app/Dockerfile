# Demo 36: Kanboard
# Self-hosted Kanban project management
# https://kanboard.org/

FROM kanboard/kanboard:v1.2.40

# Kanboard configuration for MySQL
# Environment variables are set at runtime via Hop3

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Default port
EXPOSE 80

# Use our startup script to parse DATABASE_URL
CMD ["/usr/local/bin/start.sh"]
