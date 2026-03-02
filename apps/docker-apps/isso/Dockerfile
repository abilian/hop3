# Isso Dockerfile for Hop3
# Lightweight commenting system

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies (python3-setuptools provides pkg_resources for Python 3.13)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-setuptools \
    build-essential \
    libffi-dev \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Create isso user
RUN useradd -m -d /var/lib/isso -s /bin/bash isso

# Create directories
RUN mkdir -p /var/lib/isso/db /etc/isso \
    && chown -R isso:isso /var/lib/isso /etc/isso

# Install Isso in venv with system site-packages (for pkg_resources access)
RUN python3 -m venv --system-site-packages /opt/isso \
    && /opt/isso/bin/pip install --no-cache-dir isso gunicorn

# Create default config
RUN echo '[general]\n\
dbpath = /var/lib/isso/db/comments.db\n\
host = http://localhost:8080\n\
\n\
[server]\n\
listen = http://0.0.0.0:8080\n\
\n\
[moderation]\n\
enabled = false\n\
\n\
[guard]\n\
enabled = true\n\
ratelimit = 2\n\
direct-reply = 3\n\
reply-to-self = false\n\
require-author = false\n\
require-email = false\n\
\n\
[markup]\n\
options = strikethrough, superscript, autolink\n\
allowed-elements = \n\
allowed-attributes = \n\
\n\
[hash]\n\
salt = change-me-to-random-string\n\
algorithm = pbkdf2\n\
' > /etc/isso/isso.cfg \
    && chown isso:isso /etc/isso/isso.cfg

# Copy startup script
COPY start-isso.sh /usr/local/bin/start-isso.sh
RUN chmod +x /usr/local/bin/start-isso.sh

# Environment (PORT is required, no default)

# Data volume
VOLUME /var/lib/isso/db

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start-isso.sh"]
