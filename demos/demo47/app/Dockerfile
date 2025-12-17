# Demo 47: Minimal Ruby/Sinatra with MySQL
# Test Ruby + mysql2 gem connectivity

FROM ruby:3.2-alpine

# Install build dependencies for mysql2 gem
RUN apk add --no-cache \
    build-base \
    mysql-dev \
    mysql-client

WORKDIR /app

# Install gems
COPY Gemfile ./
RUN bundle install

# Copy application
COPY app.rb ./

EXPOSE 4567

CMD ["ruby", "app.rb"]
