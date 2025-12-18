# Demo 49: Taiga - Agile Project Management
# Build from source for ARM64 compatibility

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        nginx \
        supervisor \
        curl \
        gettext-base \
        git \
        libpq-dev \
        gcc \
        g++ \
        libc-dev \
        libffi-dev \
        libjpeg-dev \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
        libfreetype6-dev \
        libcairo2-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/nginx

# Set up taiga user
RUN useradd -m -d /home/taiga -s /bin/bash taiga

# Clone Taiga backend
ARG TAIGA_BACK_VERSION=6.8.1
ARG TAIGA_FRONT_VERSION=6.8.1
WORKDIR /taiga-back
RUN git clone --depth 1 --branch ${TAIGA_BACK_VERSION} https://github.com/taigaio/taiga-back.git . && \
    # Remove heavy image processing deps (optional for basic usage)
    sed -i '/scikit-image/d' requirements.txt && \
    sed -i '/aggdraw/d' requirements.txt && \
    pip install --no-cache-dir --prefer-binary -r requirements.txt && \
    pip install --no-cache-dir gunicorn psycopg2-binary && \
    chown -R taiga:taiga /taiga-back

# Download Taiga frontend (note: tags are just version numbers, not VERSION-stable)
RUN mkdir -p /var/www/taiga && \
    curl -sL https://github.com/taigaio/taiga-front-dist/archive/refs/tags/${TAIGA_FRONT_VERSION}.tar.gz | \
    tar xz --strip-components=2 -C /var/www/taiga

# Copy configuration files
COPY nginx.conf /etc/nginx/nginx.conf
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY conf.json.template /var/www/taiga/conf.json.template
COPY local.py /taiga-back/settings/local.py
COPY --chmod=755 start.sh /start.sh

EXPOSE 80

CMD ["/start.sh"]
