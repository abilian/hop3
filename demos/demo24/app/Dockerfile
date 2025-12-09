# Demo 24: Listmonk
# A high-performance newsletter and mailing list manager with PostgreSQL

FROM listmonk/listmonk:latest

# Copy startup script
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 9000

CMD ["/start.sh"]
