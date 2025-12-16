# Demo 28: MySQL Page Counter

A simple Flask application that demonstrates the MySQL addon functionality with a page view counter.

## Purpose

This demo validates that the MySQL addon works correctly by:
1. Creating a MySQL database via `hop3 addons:create mysql`
2. Attaching the database to a Docker application
3. Performing basic CRUD operations (create table, insert, update, query)

## Application Features

- **Page Counter**: Tracks page views in MySQL
- **Database Status**: Shows MySQL connection status and version
- **Counter Statistics**: Lists all tracked pages with view counts

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `/` | Home page - increments counter on each visit |
| `/db-status` | Check MySQL connection status |
| `/db-init` | Initialize database table |
| `/counter` | Get all page view statistics |
| `/db-test` | Test database operations |
| `/health` | Health check endpoint |

## Manual Testing

```bash
# Deploy the app (from the app directory)
cd demos/demo28/app
hop3 deploy demo28

# Set hostname
hop3 config:set demo28 HOST_NAME=demo28.example.com

# Redeploy to apply hostname
hop3 deploy demo28

# Create and attach MySQL database
hop3 addons:create mysql demo28-db
hop3 addons:attach demo28-db --app demo28 --service-type mysql

# Redeploy to pick up env vars
hop3 deploy demo28

# Initialize database
curl https://demo28.example.com/db-init

# Test counter
curl https://demo28.example.com/
curl https://demo28.example.com/
curl https://demo28.example.com/counter

# Cleanup
hop3 addons:detach demo28-db --app demo28 --service-type mysql
hop3 addons:destroy demo28-db --service-type mysql
hop3 app:destroy demo28 -y
```

## Server Requirements

- MySQL server installed and running
- Environment variable `MYSQL_SUPERUSER_PASSWORD` set to MySQL root password

## Files

- `app/app.py` - Flask application with MySQL page counter
- `app/Dockerfile` - Docker image definition
- `app/requirements.txt` - Python dependencies
- `app/hop3.toml` - Hop3 configuration
- `demo-script.py` - Automated demo script
