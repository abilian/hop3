# Demo 44: Redmine
# Project management web application
# https://www.redmine.org/

FROM redmine:5.1-alpine

# Copy wrapper script that maps env vars and calls original entrypoint
# Note: Alpine uses /bin/sh, not /bin/bash
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Default port
EXPOSE 3000

# Override entrypoint to map env vars, then call original docker-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/start.sh"]
CMD ["rails", "server", "-b", "0.0.0.0"]
