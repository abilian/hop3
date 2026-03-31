# frozen_string_literal: true

require 'sinatra'

# Configure server binding
set :bind, ENV.fetch('BIND_ADDRESS', '127.0.0.1')
set :port, ENV.fetch('PORT', 4567).to_i

get '/' do
  'Hello World, from Sinatra via Nix!'
end
