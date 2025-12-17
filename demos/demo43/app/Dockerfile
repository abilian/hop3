# Demo 43: EasyAppointments
# Open-source appointment scheduling
# https://easyappointments.org/

FROM alextselegidis/easyappointments:latest

# Copy wrapper script that maps env vars and calls original entrypoint
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Default port
EXPOSE 80

# Override entrypoint to map env vars, then call original docker-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/start.sh"]
