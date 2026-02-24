# Discourse Dockerfile for Hop3
# Open source discussion platform

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install build dependencies for Ruby and Discourse
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
    imagemagick \
    optipng \
    pngquant \
    jhead \
    jpegoptim \
    gifsicle \
    git \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 18 and yarn
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g yarn \
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

# Create discourse user
RUN useradd -m -s /bin/bash discourse

WORKDIR /home/discourse/app

# Download Discourse (use latest stable)
ARG DISCOURSE_VERSION=3.2.5
RUN curl -sL "https://github.com/discourse/discourse/archive/refs/tags/v${DISCOURSE_VERSION}.tar.gz" | tar xz --strip-components=1

# Set Rails environment
ENV RAILS_ENV=production
ENV DISCOURSE_HOSTNAME=localhost

# Install dependencies (quietly) - uses yarn, not npm
RUN bundle config set --local deployment 'true' \
    && bundle config set --local without 'test development' \
    && bundle install --quiet \
    && yarn install --production --silent \
    && chown -R discourse:discourse /home/discourse

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
cd /home/discourse/app\n\
\n\
# Set environment variables\n\
export RAILS_ENV=production\n\
export DISCOURSE_HOSTNAME="${DISCOURSE_HOSTNAME:-localhost}"\n\
export DISCOURSE_DB_HOST="${PGHOST:-localhost}"\n\
export DISCOURSE_DB_PORT="${PGPORT:-5432}"\n\
export DISCOURSE_DB_NAME="${PGDATABASE:-discourse}"\n\
export DISCOURSE_DB_USERNAME="${PGUSER:-discourse}"\n\
export DISCOURSE_DB_PASSWORD="${PGPASSWORD}"\n\
export DISCOURSE_REDIS_HOST="${REDIS_HOST:-localhost}"\n\
export DISCOURSE_REDIS_PORT="${REDIS_PORT:-6379}"\n\
export SECRET_KEY_BASE="${SECRET_KEY_BASE:-$(head -c 64 /dev/urandom | base64)}"\n\
\n\
# Precompile assets\n\
bundle exec rake assets:precompile\n\
\n\
# Run migrations\n\
bundle exec rake db:migrate\n\
\n\
# Start Discourse\n\
exec su discourse -c "cd /home/discourse/app && bundle exec rails server -b 0.0.0.0 -p ${PORT:-8080}"\n\
' > /usr/local/bin/start-discourse.sh \
    && chmod +x /usr/local/bin/start-discourse.sh

ENV PORT=8080
EXPOSE 8080

CMD ["/usr/local/bin/start-discourse.sh"]
