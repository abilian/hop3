# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
#
# Demo 52: Native Ruby/Sinatra application
# Feature-rich API similar to demo50/51

require 'bundler/setup'
require 'sinatra'
require 'sinatra/json'
require 'time'

# Configuration
set :port, ENV['PORT'].to_i if ENV.fetch('PORT', 0).to_i > 0
set :bind, ENV.fetch('BIND_ADDRESS', '127.0.0.1')

# Application state
$start_time = Time.now
$request_count = 0

# Home endpoint
get '/' do
  json(
    app: 'demo52',
    type: 'native-ruby',
    message: 'Welcome to demo52 - Native Ruby/Sinatra!',
    runtime: "Ruby #{RUBY_VERSION}"
  )
end

# Info endpoint
get '/info' do
  json(
    ruby_version: RUBY_VERSION,
    ruby_platform: RUBY_PLATFORM,
    sinatra_version: Sinatra::VERSION,
    env: {
      RACK_ENV: ENV.fetch('RACK_ENV', 'development'),
      PORT: settings.port
    }
  )
end

# Stats endpoint
get '/stats' do
  $request_count += 1
  uptime = (Time.now - $start_time).to_i

  json(
    requests: $request_count,
    uptime_seconds: uptime,
    started_at: $start_time.iso8601
  )
end

# Echo endpoint (POST)
post '/echo' do
  request.body.rewind
  body = request.body.read

  begin
    received = JSON.parse(body)
  rescue JSON::ParserError
    received = body
  end

  json(
    received: received,
    headers: {
      'content-type': request.content_type,
      'user-agent': request.user_agent
    }
  )
end

# Calculator endpoint
get '/calculate/:operation/:a/:b' do
  operation = params[:operation]
  a = params[:a].to_f
  b = params[:b].to_f

  result = case operation
  when 'add'
    a + b
  when 'subtract'
    a - b
  when 'multiply'
    a * b
  when 'divide'
    if b == 0
      halt 400, json(error: 'Division by zero')
    end
    a / b
  else
    halt 400, json(error: 'Unknown operation')
  end

  json(
    operation: operation,
    a: a,
    b: b,
    result: result
  )
end

# Fibonacci endpoint
get '/fib/:n' do
  n = params[:n].to_i

  if n < 0 || n > 40
    halt 400, json(error: 'n must be between 0 and 40')
  end

  start = Time.now
  result = fibonacci(n)
  duration = ((Time.now - start) * 1000).to_i

  json(
    n: n,
    result: result,
    duration_ms: duration
  )
end

# Health check
get '/health' do
  json(status: 'healthy')
end

# Helper function
def fibonacci(n)
  return n if n <= 1
  fibonacci(n - 1) + fibonacci(n - 2)
end
