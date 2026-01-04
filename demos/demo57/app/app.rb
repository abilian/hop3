# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

require 'sinatra'
require 'json'

# Configuration
set :bind, '0.0.0.0'
set :port, ENV['PORT'] || 4567

# Disable all Rack protection (nginx handles security)
disable :protection

# Welcome page
get '/' do
  content_type :html
  <<-HTML
  <!DOCTYPE html>
  <html>
  <head><title>Ruby Prerequisite Test</title></head>
  <body style="font-family: sans-serif; text-align: center; padding: 2rem;">
    <h1>Ruby Prerequisites OK</h1>
    <p>Ruby version: #{RUBY_VERSION}</p>
    <p>Sinatra version: #{Sinatra::VERSION}</p>
  </body>
  </html>
  HTML
end

get '/up' do
  'OK'
end

get '/health' do
  content_type :json
  JSON.generate({
    status: 'ok',
    ruby_version: RUBY_VERSION,
    sinatra_version: Sinatra::VERSION
  })
end
