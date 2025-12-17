# Demo 45: Minimal Ruby/Sinatra with PostgreSQL
# Test Ruby + PostgreSQL connectivity

FROM ruby:3.2-alpine

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
