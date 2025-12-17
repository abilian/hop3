# Demo 47: Minimal Ruby/Sinatra + MySQL connectivity test
require 'sinatra'
require 'mysql2'

set :bind, '0.0.0.0'
set :port, 4567

# Disable host authorization check (allow any hostname)
set :host_authorization, { permitted_hosts: [] }

get '/' do
  content_type :html

  host = ENV['MYSQL_HOST'] || 'localhost'
  port = (ENV['MYSQL_PORT'] || '3306').to_i
  database = ENV['MYSQL_DATABASE'] || 'demo47'
  user = ENV['MYSQL_USER'] || 'demo47'
  password = ENV['MYSQL_PASSWORD'] || ''

  html = <<~HTML
    <!DOCTYPE html>
    <html>
    <head>
      <title>Demo 47: Ruby/Sinatra + MySQL</title>
    </head>
    <body>
      <h1>Demo 47: Ruby/Sinatra + MySQL</h1>
      <p>This is a minimal Ruby app testing MySQL connectivity.</p>

      <h2>Database Connection Test</h2>
  HTML

  begin
    # Try connecting with SSL disabled
    client = Mysql2::Client.new(
      host: host,
      port: port,
      database: database,
      username: user,
      password: password,
      ssl_mode: :disabled
    )

    html += "<p style='color: green;'>Connected successfully!</p>"

    # Get MySQL version
    result = client.query("SELECT VERSION() as version")
    row = result.first
    html += "<p>MySQL Version: #{row['version']}</p>"

    client.close
  rescue => e
    html += "<p style='color: red;'>Error: #{e.message}</p>"
    html += "<p style='color: orange;'>Error class: #{e.class}</p>"
  end

  html += <<~HTML
      <h2>Environment</h2>
      <ul>
        <li>MYSQL_HOST: #{host}</li>
        <li>MYSQL_PORT: #{port}</li>
        <li>MYSQL_DATABASE: #{database}</li>
        <li>MYSQL_USER: #{user}</li>
      </ul>
    </body>
    </html>
  HTML

  html
end
