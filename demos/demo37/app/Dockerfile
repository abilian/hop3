# Demo 37: WordPress
# The world's most popular CMS
# https://wordpress.org/

FROM wordpress:6.7-apache

# WordPress configuration via environment variables
# Database settings are injected at runtime via Hop3

# Copy custom startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Default port
EXPOSE 80

CMD ["/usr/local/bin/start.sh"]
