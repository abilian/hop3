require 'sinatra'
require 'pg'
require 'json'

set :bind, '0.0.0.0'
set :port, 4567

# Disable host authorization check (allow any hostname)
set :host_authorization, { permitted_hosts: [] }

# Database connection helper using PG* environment variables from Hop3
def db_connect
  PG.connect(
    host: ENV['PGHOST'] || 'localhost',
    port: ENV['PGPORT'] || 5432,
    dbname: ENV['PGDATABASE'] || 'demo45',
    user: ENV['PGUSER'] || 'demo45',
    password: ENV['PGPASSWORD'] || ''
  )
end

get '/' do
  content_type :html
  <<-HTML
  <!DOCTYPE html>
  <html>
  <head><title>Demo 45: Ruby + PostgreSQL</title></head>
  <body>
    <h1>Demo 45: Ruby/Sinatra + PostgreSQL</h1>
    <p>This is a minimal Ruby app testing PostgreSQL connectivity.</p>
    <p><a href="/db">Check database connection</a></p>
  </body>
  </html>
  HTML
end

get '/health' do
  'OK'
end

get '/db' do
  content_type :json
  begin
    conn = db_connect
    result = conn.exec("SELECT version()")
    version = result[0]['version']
    conn.close
    { status: 'connected', postgresql_version: version }.to_json
  rescue => e
    status 500
    { status: 'error', message: e.message }.to_json
  end
end
