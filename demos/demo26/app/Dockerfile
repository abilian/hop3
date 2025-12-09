# Demo 26: Miniflux
# A minimalist and opinionated RSS reader with PostgreSQL

FROM miniflux/miniflux:latest

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 8080

CMD ["/start.sh"]
