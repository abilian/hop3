# Deploying .NET on Hop3

A .NET web app on Hop3 is your published application running as a long-lived Kestrel process. On each deploy Hop3 restores and publishes your project on the server, then starts the resulting DLL (or self-contained binary), which listens on a port Hop3 assigns at runtime. nginx sits in front and proxies your app's hostname to that process. You deploy with `hop3 deploy --app <app>`, point a hostname at it, and the platform handles the build, the process, and the reverse proxy.

This page covers the concepts shared by every .NET deployment. Read it first, then follow the framework guide below for a complete, runnable walkthrough.

## How Hop3 builds and runs .NET

Hop3 builds .NET apps with the **.NET SDK** on the server — you declare the SDK as a build package, and the build step runs `dotnet publish` to produce a self-contained `publish/` directory. There is no separate application server like uWSGI: ASP.NET Core ships its own production web server, **Kestrel**, and Hop3 simply runs your published app as the web process.

The one rule that makes everything work is the port. Hop3 injects a `PORT` environment variable for each app, and your app must bind Kestrel to it instead of a hardcoded port. ASP.NET Core does not read `PORT` automatically, so you wire it up in `Program.cs`:

```csharp
var port = Environment.GetEnvironmentVariable("PORT") ?? "5000";
builder.WebHost.UseUrls($"http://0.0.0.0:{port}");
```

With that in place, a typical `hop3.toml` looks like this:

```toml
[metadata]
id = "my-dotnet-app"
version = "1.0.0"
title = "My ASP.NET Core Application"

[build]
before-build = ["dotnet publish -c Release -o publish"]
packages = ["dotnet-sdk-8.0"]

[run]
start = "dotnet publish/my-dotnet-app.dll"

[env]
ASPNETCORE_ENVIRONMENT = "Production"

[port]
web = 5000

[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

The flow is: `before-build` runs `dotnet publish` to produce `publish/`, `[run].start` launches the published DLL with `dotnet`, the app binds Kestrel to the injected `$PORT`, and nginx proxies the app's hostname to it. The `[healthcheck]` path is hit to confirm the process is live — add a tiny endpoint like `app.MapGet("/up", () => "OK")` for it.

## Cross-cutting notes

These apply to every .NET app on Hop3, regardless of how your project is structured:

- **Set `ASPNETCORE_ENVIRONMENT=Production`** in `[env]` so the framework runs with production logging and error handling.
- **Addons are exposed as environment variables.** Attach PostgreSQL or Redis and read the injected connection strings in `Program.cs` — for example `Environment.GetEnvironmentVariable("DATABASE_URL")` for Npgsql, or `REDIS_URL` for the StackExchange Redis cache. Don't hardcode credentials.
- **Run database migrations on deploy** with a `before-run` step such as `dotnet ef database update || true`, so the schema is current before the new process takes traffic.
- **Choose your publish style.** The default framework-dependent publish needs the matching `dotnet-sdk-*` package on the server. A self-contained or Native AOT publish (`-r linux-x64 --self-contained`) ships the runtime with your app and starts the binary directly (`./publish/my-dotnet-app`) for faster startup and a smaller footprint.
- **Scale the web process** with `hop3 ps scale --app <app> web=2` once a single instance is healthy.
- **Don't commit build output.** Add `bin/`, `obj/`, and `publish/` to `.gitignore`; Hop3 rebuilds them on the server.

## Choose a framework

| Framework | Description |
|-----------|-------------|
| [ASP.NET Core](aspnet-core.md) | The standard cross-platform framework for .NET web apps and APIs, served by Kestrel. |
