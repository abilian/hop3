# Demo 24: Listmonk
# A high-performance newsletter and mailing list manager with PostgreSQL

FROM listmonk/listmonk:latest

# Install Python for startup script (listmonk is based on Alpine)
RUN apk add --no-cache python3

# Copy startup script
COPY start.py /start.py

EXPOSE 9000

CMD ["python3", "/start.py"]
