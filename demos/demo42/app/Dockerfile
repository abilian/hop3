# Demo 42: LimeSurvey
# Open-source survey tool
# https://www.limesurvey.org/

FROM martialblog/limesurvey:6-apache

# Copy startup script with execute permission (rootless image)
COPY --chmod=755 start.sh /usr/local/bin/start.sh

# Default port (martialblog image uses 8080)
EXPOSE 8080

# Use our startup script, pass apache2-foreground as CMD
ENTRYPOINT ["/usr/local/bin/start.sh"]
CMD ["apache2-foreground"]
