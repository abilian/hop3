# Mastodon Dockerfile for Hop3
# Open source social network

FROM debian:bookworm-slim

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
    nodejs \
    npm \
    git \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g yarn

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

# Install dependencies
RUN bundle config set --local deployment 'true' \
    && bundle config set --local without 'test development' \
    && bundle install \
    && yarn install --production \
    && chown -R mastodon:mastodon /home/mastodon

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
cd /home/mastodon/app\n\
\n\
# Set environment variables\n\
export RAILS_ENV=production\n\
export LOCAL_DOMAIN="${LOCAL_DOMAIN:-localhost}"\n\
export DB_HOST="${PGHOST:-localhost}"\n\
export DB_PORT="${PGPORT:-5432}"\n\
export DB_NAME="${PGDATABASE:-mastodon_production}"\n\
export DB_USER="${PGUSER:-mastodon}"\n\
export DB_PASS="${PGPASSWORD}"\n\
export REDIS_HOST="${REDIS_HOST:-localhost}"\n\
export REDIS_PORT="${REDIS_PORT:-6379}"\n\
export SECRET_KEY_BASE="${SECRET_KEY_BASE:-$(head -c 64 /dev/urandom | base64)}"\n\
export OTP_SECRET="${OTP_SECRET:-$(head -c 64 /dev/urandom | base64)}"\n\
\n\
# Precompile assets\n\
RAILS_ENV=production bundle exec rails assets:precompile\n\
\n\
# Run migrations\n\
RAILS_ENV=production bundle exec rails db:migrate\n\
\n\
# Start Mastodon web\n\
exec su mastodon -c "cd /home/mastodon/app && bundle exec puma -C config/puma.rb -b tcp://0.0.0.0:${PORT:-8080}"\n\
' > /usr/local/bin/start-mastodon.sh \
    && chmod +x /usr/local/bin/start-mastodon.sh

ENV PORT=8080
EXPOSE 8080

CMD ["/usr/local/bin/start-mastodon.sh"]
