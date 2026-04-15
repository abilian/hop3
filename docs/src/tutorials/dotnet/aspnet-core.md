# Deploying ASP.NET Core on Hop3

This guide walks you through deploying an ASP.NET Core application on Hop3. By the end, you'll have a production-ready .NET application running on your own infrastructure.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/installation.md) if you haven't set one up yet
2. **The Hop3 CLI** - Installed on your local machine
3. **.NET SDK 8.0+** - Install from [dot.net](https://dot.net/)
4. **Git** - For version control and deployment

Verify your local setup:

```bash
dotnet --version
```

```bash
dotnet --list-sdks | head -1
```

## Step 1: Create a New ASP.NET Core Application

Create a new web API project:

```bash
dotnet new webapi -n hop3-tuto-aspnet-core --no-https --framework net8.0
```

```console
The template "ASP.NET Core Web API" was created successfully
```

Verify the project structure:

```bash
ls -la
```

```console
hop3-tuto-aspnet-core.csproj
```

```console
Program.cs
```

Install required packages (Swagger support was removed from .NET 9 templates):

```bash
dotnet add package Swashbuckle.AspNetCore
```

```console
PackageReference for package 'Swashbuckle.AspNetCore'
```

## Step 2: Configure the Application

Update `Program.cs` with health endpoints and proper configuration:

```csharp
using System.Diagnostics;
using System.Runtime.InteropServices;

var builder = WebApplication.CreateBuilder(args);

// Add services
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();
builder.Services.AddHealthChecks();

// Configure Kestrel to use PORT environment variable
var port = Environment.GetEnvironmentVariable("PORT") ?? "5000";
builder.WebHost.UseUrls($"http://0.0.0.0:{port}");

var app = builder.Build();

// Enable Swagger in all environments for this demo
app.UseSwagger();
app.UseSwaggerUI();

// Welcome page
app.MapGet("/", () => Results.Content($@"
<!DOCTYPE html>
<html>
<head>
    <title>Welcome to Hop3</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #512BD4 0%, #68217A 100%);
            color: white;
        }}
        .container {{ text-align: center; padding: 2rem; }}
        h1 {{ font-size: 3rem; margin-bottom: 1rem; }}
        p {{ font-size: 1.25rem; opacity: 0.9; }}
        a {{
            display: inline-block;
            margin-top: 1rem;
            padding: 0.75rem 1.5rem;
            background: rgba(255,255,255,0.2);
            border-radius: 8px;
            color: white;
            text-decoration: none;
        }}
    </style>
</head>
<body>
    <div class='container'>
        <h1>Hello from Hop3!</h1>
        <p>Your ASP.NET Core application is running.</p>
        <p>Current time: {DateTime.UtcNow:O}</p>
        <a href='/swagger'>API Documentation</a>
        <a href='/api/info'>API Info</a>
    </div>
</body>
</html>
", "text/html"));

// Health check endpoints
app.MapGet("/up", () => "OK");

app.MapGet("/health", () => new
{
    Status = "ok",
    Timestamp = DateTime.UtcNow,
    Uptime = (DateTime.UtcNow - Process.GetCurrentProcess().StartTime.ToUniversalTime()).ToString(),
    Memory = new
    {
        WorkingSet = $"{Process.GetCurrentProcess().WorkingSet64 / 1024 / 1024}MB",
        GCMemory = $"{GC.GetTotalMemory(false) / 1024 / 1024}MB"
    }
});

// API info endpoint
app.MapGet("/api/info", () => new
{
    Name = "hop3-tuto-aspnet-core",
    Version = "1.0.0",
    DotNetVersion = RuntimeInformation.FrameworkDescription,
    OS = RuntimeInformation.OSDescription,
    Architecture = RuntimeInformation.ProcessArchitecture.ToString()
});

// Example CRUD endpoints
var items = new Dictionary<int, Item>
{
    { 1, new Item(1, "Item 1", "First item", 9.99m) },
    { 2, new Item(2, "Item 2", "Second item", 19.99m) }
};
var nextId = 3;

app.MapGet("/api/items", () => items.Values);

app.MapGet("/api/items/{id}", (int id) =>
    items.TryGetValue(id, out var item) ? Results.Ok(item) : Results.NotFound());

app.MapPost("/api/items", (ItemCreateRequest request) =>
{
    var item = new Item(nextId++, request.Name, request.Description, request.Price);
    items[item.Id] = item;
    return Results.Created($"/api/items/{item.Id}", item);
});

app.MapPut("/api/items/{id}", (int id, ItemCreateRequest request) =>
{
    if (!items.ContainsKey(id)) return Results.NotFound();
    var item = new Item(id, request.Name, request.Description, request.Price);
    items[id] = item;
    return Results.Ok(item);
});

app.MapDelete("/api/items/{id}", (int id) =>
{
    if (!items.Remove(id)) return Results.NotFound();
    return Results.NoContent();
});

// Map health checks endpoint
app.MapHealthChecks("/healthz");

app.Run();

// Records for data models
record Item(int Id, string Name, string? Description, decimal Price);
record ItemCreateRequest(string Name, string? Description, decimal Price);
```

Remove the default weather controller:

```bash
rm -f Controllers/WeatherForecastController.cs WeatherForecast.cs 2>/dev/null || true
```

## Step 3: Build and Test

Build the application:

```bash
dotnet build
```

```console
Build succeeded
```

Test the application:

```bash
dotnet run > /dev/null 2>&1 &
APP_PID=$!
sleep 8
curl -s http://localhost:5000/up || echo "Server not responding"
kill $APP_PID 2>/dev/null || true
```

```console
OK
```

## Step 4: Publish for Production

Publish a self-contained deployment:

```bash
dotnet publish -c Release -o publish
```

```console
hop3-tuto-aspnet-core ->
```

Verify the publish output:

```bash
ls -la publish/
```

```console
hop3-tuto-aspnet-core.dll
```

## Step 5: Create Deployment Configuration

### Create a Procfile

```procfile
# Pre-build: Restore and publish
prebuild: dotnet publish -c Release -o publish

# Main web process
web: dotnet publish/hop3-tuto-aspnet-core.dll
```

### Create hop3.toml

```toml
[metadata]
id = "hop3-tuto-aspnet-core"
version = "1.0.0"
title = "My ASP.NET Core Application"

[build]
before-build = ["dotnet publish -c Release -o publish"]
packages = ["dotnet-sdk-8.0"]

[run]
start = "dotnet publish/hop3-tuto-aspnet-core.dll"

[env]
ASPNETCORE_ENVIRONMENT = "Production"
DOTNET_RUNNING_IN_CONTAINER = "true"

[port]
web = 5000

[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

Verify the deployment files:

```bash
ls -la Procfile hop3.toml
```

```console
Procfile
```

```console
hop3.toml
```

## Step 6: Initialize Git Repository

```text
# Build output
bin/
obj/
publish/

# IDE
.idea/
.vscode/
*.user
*.suo

# Environment
.env
appsettings.*.json
!appsettings.json

# OS
.DS_Store
Thumbs.db

# Logs
*.log
logs/
```

```bash
git init
```

```console
Initialized empty Git repository
```

```bash
git add .
```

```bash
git commit -m "Initial ASP.NET Core application"
```

```console
Initial ASP.NET Core application
```

## Step 7: Deploy to Hop3

The following steps require a Hop3 server.

### Initialize (First Time Only)

```bash
hop3 init --ssh root@your-server.example.com
```

### Set Environment Variables

```bash
hop3 config set hop3-tuto-aspnet-core ASPNETCORE_ENVIRONMENT=Production
```

### Deploy

Deploy the application (first deployment creates the app):

```bash
hop3 deploy hop3-tuto-aspnet-core
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 config set hop3-tuto-aspnet-core HOST_NAME=hop3-tuto-aspnet-core.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash
hop3 deploy hop3-tuto-aspnet-core
```

Wait for the application to start:

```bash
sleep 5
```

### Verify Deployment

```bash
hop3 app status hop3-tuto-aspnet-core
```

```console
hop3-tuto-aspnet-core
```

```bash
curl -s http://hop3-tuto-aspnet-core.$HOP3_TEST_DOMAIN/up
```

```console
OK
```

View logs:

```bash
# View logs
hop3 app logs hop3-tuto-aspnet-core

# Your app will be available at:
# http://hop3-tuto-aspnet-core.your-hop3-server.example.com
```

### Managing Your Application

```bash
# Restart the application
hop3 app restart hop3-tuto-aspnet-core

# View/set environment variables
hop3 config show hop3-tuto-aspnet-core
hop3 config set hop3-tuto-aspnet-core NEW_VAR=value

# Scale workers
hop3 ps scale hop3-tuto-aspnet-core web=2
```

## Advanced Configuration

### Adding Entity Framework Core with PostgreSQL

```bash
dotnet add package Npgsql.EntityFrameworkCore.PostgreSQL
dotnet add package Microsoft.EntityFrameworkCore.Design
```

Create a DbContext:

```csharp
// Data/AppDbContext.cs
using Microsoft.EntityFrameworkCore;

public class AppDbContext : DbContext
{
    public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }

    public DbSet<User> Users => Set<User>();
}

public class User
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public string Email { get; set; } = "";
}
```

Configure in Program.cs:

```csharp
var connectionString = Environment.GetEnvironmentVariable("DATABASE_URL")
    ?? builder.Configuration.GetConnectionString("DefaultConnection");

builder.Services.AddDbContext<AppDbContext>(options =>
    options.UseNpgsql(connectionString));
```

### Adding Redis Caching

```bash
dotnet add package Microsoft.Extensions.Caching.StackExchangeRedis
```

```csharp
builder.Services.AddStackExchangeRedisCache(options =>
{
    options.Configuration = Environment.GetEnvironmentVariable("REDIS_URL");
});
```

### JWT Authentication

```bash
dotnet add package Microsoft.AspNetCore.Authentication.JwtBearer
```

```csharp
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true,
            ValidateAudience = true,
            ValidateLifetime = true,
            ValidIssuer = builder.Configuration["Jwt:Issuer"],
            ValidAudience = builder.Configuration["Jwt:Audience"],
            IssuerSigningKey = new SymmetricSecurityKey(
                Encoding.UTF8.GetBytes(Environment.GetEnvironmentVariable("JWT_SECRET")!))
        };
    });
```

### Background Services

```csharp
// Services/BackgroundWorker.cs
public class BackgroundWorker : BackgroundService
{
    private readonly ILogger<BackgroundWorker> _logger;

    public BackgroundWorker(ILogger<BackgroundWorker> logger)
    {
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            _logger.LogInformation("Worker running at: {time}", DateTimeOffset.Now);
            await Task.Delay(60000, stoppingToken);
        }
    }
}

// In Program.cs
builder.Services.AddHostedService<BackgroundWorker>();
```

### Self-Contained Deployment

For deployment without .NET runtime on server:

```bash
dotnet publish -c Release -r linux-x64 --self-contained -o publish
```

Update hop3.toml:

```toml
[build]
before-build = ["dotnet publish -c Release -r linux-x64 --self-contained -o publish"]

[run]
start = "./publish/hop3-tuto-aspnet-core"
```

### Native AOT (Ahead-of-Time Compilation)

For faster startup and smaller memory footprint:

```xml
<!-- In hop3-tuto-aspnet-core.csproj -->
<PropertyGroup>
    <PublishAot>true</PublishAot>
</PropertyGroup>
```

```bash
dotnet publish -c Release -r linux-x64
```

## Troubleshooting

### Port Binding Issues
Ensure PORT environment variable is used:

```csharp
var port = Environment.GetEnvironmentVariable("PORT") ?? "5000";
builder.WebHost.UseUrls($"http://0.0.0.0:{port}");
```

### Database Connection Issues
Check connection string format:

```
Host=localhost;Database=hop3-tuto-aspnet-core;Username=user;Password=pass
```

### Memory Issues
.NET is generally efficient, but monitor with `/health` endpoint. Set memory limits:

```bash
hop3 config set hop3-tuto-aspnet-core DOTNET_GCHeapHardLimit=268435456
```

### Slow Startup
Consider using Native AOT or ReadyToRun compilation:

```bash
dotnet publish -c Release -p:PublishReadyToRun=true
```

## Example Files

### Complete hop3.toml

```toml
[metadata]
id = "hop3-tuto-aspnet-core"
version = "1.0.0"
title = "My ASP.NET Core Application"

[build]
before-build = ["dotnet publish -c Release -o publish"]
packages = ["dotnet-sdk-8.0"]

[run]
start = "dotnet publish/hop3-tuto-aspnet-core.dll"
before-run = "dotnet ef database update || true"

[env]
ASPNETCORE_ENVIRONMENT = "Production"
DOTNET_RUNNING_IN_CONTAINER = "true"

[port]
web = 5000

[healthcheck]
path = "/healthz"
timeout = 30
interval = 60

[[provider]]
name = "postgres"
plan = "standard"

[[provider]]
name = "redis"
plan = "basic"
```

### Complete Procfile

```procfile
prebuild: dotnet publish -c Release -o publish
prerun: dotnet ef database update --project publish/hop3-tuto-aspnet-core.dll || true
web: dotnet publish/hop3-tuto-aspnet-core.dll
worker: dotnet publish/hop3-tuto-aspnet-core.dll --worker
```

### appsettings.json

```json
{
  "Logging": {
    "LogLevel": {
      "Default": "Information",
      "Microsoft.AspNetCore": "Warning"
    }
  },
  "AllowedHosts": "*",
  "ConnectionStrings": {
    "DefaultConnection": ""
  }
}
```
