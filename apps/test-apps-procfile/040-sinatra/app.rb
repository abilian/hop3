require 'bundler/setup'
require 'sinatra'

set :port, ENV['PORT'].to_i if ENV.fetch('PORT', 0).to_i > 0

get '/' do
  'Hello world!'
end
