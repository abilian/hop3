FROM matomo:5-apache

# Set up directories
RUN mkdir -p /var/www/html/tmp \
    && chown -R www-data:www-data /var/www/html

# Copy startup script
COPY start.py /app/start.py
RUN chmod +x /app/start.py

CMD ["python3", "/app/start.py"]
