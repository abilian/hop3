# Discourse Dockerfile for Hop3
# Open source discussion platform

FROM debian:bookworm-slim@sha256:7b140f374b289a7c2befc338f42ebe6441b7ea838a042bbd5acbfca6ec875818

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
    brotli \
    git \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 18, yarn, patch-package and terser (all needed by the Discourse build).
#
# terser is NOT optional and NOT a package.json dependency, so `yarn install` never
# provides it — it has to be global. lib/tasks/assets.rake:64 does:
#     $node_compress = `which terser`.present? && !ENV["SKIP_NODE_UGLIFY"]
# If `which terser` fails, assets:precompile:compress_js silently falls back to the
# Ruby Uglifier 4.2.0 gem, which cannot parse ES6 and dies on the first arrow
# function: "Unexpected token: operator (>)".
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g yarn patch-package terser \
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

# Install dependencies (quietly)
# Discourse build requires dev deps (postinstall hooks run patch-package, etc.)
RUN bundle config set --local deployment 'true' \
    && bundle config set --local without 'test development' \
    && bundle install --quiet \
    && yarn install --silent \
    && yarn cache clean \
    && chown -R discourse:discourse /home/discourse

# Precompile assets at BUILD time so the container binds $PORT promptly instead
# of running the multi-minute Ember/webpack compile inside the deploy health
# window. assets:precompile boots the Rails production env, which reads the
# secret-key-base from Redis (global_setting.rb `safe_secret_key_base`)
# UNCONDITIONALLY — SKIP_DB_AND_REDIS does not suppress that read. The addon
# Redis is host-side and unreachable during an isolated `docker build`, so stand
# up a throwaway redis-server just for this layer (it is never used at runtime —
# the app talks to $REDIS_HOST). A valid 128-hex SECRET_KEY_BASE is still passed
# so precompile doesn't choke on it; the runtime script generates the real one.
#
# DONT_PRECOMPILE_CSS=1 is upstream's own escape hatch (assets.rake:95). The
# assets:precompile:css task compiles themes and colour schemes *out of the
# database*, so it needs a live, migrated Postgres — which a build must not have:
# the build-time DB would not be the runtime one. Upstream handles this: "CSS will
# get precompiled during first request if tables do not exist" (assets.rake:101).
# So CSS moves to first boot; the expensive Ember/JS build stays at build time.
RUN apt-get update && apt-get install -y --no-install-recommends redis-server \
    && rm -rf /var/lib/apt/lists/* \
    && redis-server --daemonize yes \
    && SECRET_KEY_BASE=deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef \
       SKIP_DB_AND_REDIS=1 \
       DONT_PRECOMPILE_CSS=1 \
       bundle exec rake assets:precompile \
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
# Bind unicorn to all interfaces on $PORT and run one supervised Sidekiq.\n\
export UNICORN_LISTENER="0.0.0.0:${PORT:-8080}"\n\
export UNICORN_SIDEKIQS=1\n\
\n\
# Run migrations (assets are precompiled at build time)\n\
bundle exec rake db:migrate\n\
\n\
# db:migrate ran as root; hand tmp and log back to the runtime user and make\n\
# sure the dirs unicorn writes its pid and socket into exist.\n\
mkdir -p tmp/pids tmp/sockets\n\
chown -R discourse:discourse tmp log\n\
\n\
# Start Discourse under unicorn (its production web server), not rails server.\n\
# config/initializers/100-verify_config.rb only runs under rails server (it\n\
# guards on defined?(Rails::Server)); it evaluates Discourse.current_hostname\n\
# too early and crashes boot with an uninitialized-constant SiteSetting error.\n\
# unicorn never defines Rails::Server, so the check is skipped, matching how\n\
# Discourse runs in production.\n\
exec su discourse -c "cd /home/discourse/app && bundle exec unicorn -c config/unicorn.conf.rb -E production"\n\
' > /usr/local/bin/start-discourse.sh \
    && chmod +x /usr/local/bin/start-discourse.sh

ENV PORT=8080
EXPOSE 8080

CMD ["/usr/local/bin/start-discourse.sh"]
