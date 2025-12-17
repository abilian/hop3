# Demo 39: Matomo Analytics
# Open-source web analytics platform (Google Analytics alternative)
# https://matomo.org/

FROM matomo:5-apache

# Copy startup script to map env vars
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Default port
EXPOSE 80

# Use our startup script, pass apache2-foreground as CMD
ENTRYPOINT ["/usr/local/bin/start.sh"]
CMD ["apache2-foreground"]
