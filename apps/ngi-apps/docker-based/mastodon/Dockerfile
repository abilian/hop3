# Mastodon Dockerfile for Hop3
# Open source social network

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install build dependencies for Ruby and Mastodon
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    build-essential \
    libpq-dev \
    libxml2-dev \
    libxslt1-dev \
    libyaml-dev \
    libreadline-dev \
    libssl-dev \
    zlib1g-dev \
    libffi-dev \
    libgdbm-dev \
    libncurses5-dev \
    autoconf \
    bison \
    libidn11-dev \
    libicu-dev \
    imagemagick \
    ffmpeg \
    libjemalloc2 \
    git \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js and enable corepack for Yarn 4
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && corepack enable \
    && rm -rf /var/lib/apt/lists/*

# Install Ruby 3.3 from source
ARG RUBY_VERSION=3.3.0
RUN curl -fsSL "https://cache.ruby-lang.org/pub/ruby/3.3/ruby-${RUBY_VERSION}.tar.gz" | tar xz \
    && cd ruby-${RUBY_VERSION} \
    && ./configure --disable-install-doc \
    && make -j$(nproc) \
    && make install \
    && cd .. \
    && rm -rf ruby-${RUBY_VERSION} \
    && gem install bundler

# Create mastodon user
RUN useradd -m -s /bin/bash mastodon

WORKDIR /home/mastodon/app

# Download Mastodon
ARG MASTODON_VERSION=v4.3.4
RUN curl -sL "https://github.com/mastodon/mastodon/archive/refs/tags/${MASTODON_VERSION}.tar.gz" | tar xz --strip-components=1

# Set Rails environment
ENV RAILS_ENV=production
ENV NODE_ENV=production

# Install dependencies (quietly)
RUN bundle config set --local deployment 'true' \
    && bundle config set --local without 'test development' \
    && bundle install --quiet \
    && yarn install --immutable \
    && chown -R mastodon:mastodon /home/mastodon

# Precompile assets at build time (use dummy secrets - assets don't need real ones)
RUN SECRET_KEY_BASE=precompile_placeholder \
    OTP_SECRET=precompile_placeholder \
    ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY=precompile_placeholder \
    ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY=precompile_placeholder \
    ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT=precompile_placeholder \
    bundle exec rails assets:precompile \
    && chown -R mastodon:mastodon /home/mastodon

# Copy startup script
COPY start-mastodon.sh /usr/local/bin/start-mastodon.sh
RUN chmod +x /usr/local/bin/start-mastodon.sh

# Environment (PORT, PG*, and REDIS* are required, no defaults)
EXPOSE 8080

CMD ["/usr/local/bin/start-mastodon.sh"]
