# Demo 44: Redmine
# Project management web application
# https://www.redmine.org/
# Built from source on debian:bookworm-slim

FROM debian:bookworm-slim

# Install Ruby and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        ruby \
        ruby-dev \
        build-essential \
        libpq-dev \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
        imagemagick \
        libmagickwand-dev \
        curl \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/* \
    && gem install bundler -v '~> 2.5'

# Redmine version
ARG REDMINE_VERSION=5.1.10

# Download and extract Redmine
WORKDIR /usr/src/redmine
RUN curl -fsSL "https://www.redmine.org/releases/redmine-${REDMINE_VERSION}.tar.gz" | \
    tar -xz --strip-components=1 \
    && mkdir -p tmp/pdf public/plugin_assets \
    && chown -R 1000:1000 /usr/src/redmine

# Install dependencies - skip development and test gems, include PostgreSQL and Puma
RUN bundle config set --local without 'development test' \
    && echo 'gem "pg", "~> 1.5.3"' >> Gemfile.local \
    && echo 'gem "puma"' >> Gemfile.local \
    && bundle install --jobs=4

# Create non-root user
RUN useradd -m -d /usr/src/redmine -s /bin/bash -u 1000 redmine \
    && chown -R redmine:redmine /usr/src/redmine

# Copy startup script
COPY --chmod=755 start.sh /start.sh

# Runtime environment
ENV RAILS_ENV=production \
    REDMINE_HOME=/usr/src/redmine

EXPOSE 3000

USER redmine

CMD ["/start.sh"]
