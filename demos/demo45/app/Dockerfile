# Demo 45: Minimal Ruby/Sinatra with PostgreSQL
# Test Ruby + PostgreSQL connectivity

FROM ruby:3.2-alpine@sha256:d206c25708a44df6a7ce22213ee5da9fc0a9f7b31ce884429ba758db48abdc62

# Install dependencies
RUN apk add --no-cache \
    build-base \
    postgresql-dev

WORKDIR /app

# Copy and install gems
COPY Gemfile ./
RUN bundle install

# Copy application
COPY app.rb ./
COPY start.sh ./
RUN chmod +x start.sh

EXPOSE 4567

CMD ["./start.sh"]
