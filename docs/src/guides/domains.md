# Domain and Hostname Configuration

This guide explains how to configure custom domains, subdomains, and SSL certificates for your Hop3 applications.

## Overview

An app's hostnames drive the domain(s) it responds to. You can manage them in two equivalent ways:

- The first-class `hop3 domain` command group (`add`, `remove`, `set`, `list`, `clear`).
- The `HOST_NAME` environment variable, which the `domain` commands write under the hood.

When hostnames are set, Hop3 automatically:

1. Configures the reverse proxy (Nginx/Caddy/Traefik) with the appropriate virtual host settings
2. Requests and manages SSL/TLS certificates (Let's Encrypt via certbot when the engine is configured, otherwise self-signed)
3. Sets up HTTP to HTTPS redirection

## Quick Start

Set a custom domain for your app:

```bash
# Set the hostname
hop3 domain set --app myapp myapp.example.com

# Apply the change (HOST_NAME affects proxy config, so a redeploy is needed)
hop3 deploy --app myapp
```

Your app is now accessible at `https://myapp.example.com` (assuming DNS is configured).

## Configuration Options

### Single Domain

```bash
hop3 domain set --app myapp myapp.example.com
```

### Multiple Domains

Pass several hostnames to serve more than one domain:

```bash
hop3 domain set --app myapp myapp.example.com www.myapp.example.com
```

Both domains will point to the same application with the same SSL certificate. To add a hostname without replacing the existing list, use `hop3 domain add --app myapp <host>`; to drop one, use `hop3 domain remove --app myapp <host>`.

### Inspecting and Clearing Domains

```bash
# List the hostnames currently bound to an app
hop3 domain list --app myapp

# Remove all hostnames (unsets HOST_NAME)
hop3 domain clear --app myapp
```

### Using hop3.toml

You can declare an app's hostnames in its `hop3.toml` using the first-class `[domains]` section, which translates to `HOST_NAME` at deploy time:

```toml
[domains]
list = ["myapp.example.com"]
```

Or for multiple domains:

```toml
[domains]
list = ["myapp.example.com", "www.myapp.example.com"]
```

By default the listed domains are treated as defaults (existing hostnames are kept). Set `_policy = "override"` to update `HOST_NAME` on every deploy.

Setting `HOST_NAME` directly under `[env]` also works, but it is mutually exclusive with `[domains]` — declare hostnames in one place or the other, not both.

### No Domain (Direct Port Access)

If you don't set any hostname, your app won't get a reverse proxy configuration. It will only be accessible via its direct port (useful for internal services):

```bash
# Check the assigned port
hop3 app status --app myapp
```

## DNS Configuration

Before Hop3 can serve your application on a custom domain, you must configure DNS to point to your server.

### A Record

Create an A record pointing to your server's IP address:

```
Type: A
Name: myapp (or @ for root domain)
Value: YOUR_SERVER_IP
TTL: 300
```

### Wildcard DNS (Development/Staging)

For development environments, you can use wildcard DNS to automatically route all subdomains:

```
Type: A
Name: *
Value: YOUR_SERVER_IP
TTL: 300
```

This allows `*.example.com` to resolve to your Hop3 server, so `app1.example.com`, `app2.example.com`, etc. all work automatically.

### Local Development with Wildcard

For local testing, you can use services like:

- **hop3.dev** domain (if configured for development)
- **nip.io**: `myapp.127.0.0.1.nip.io` resolves to `127.0.0.1`
- **sslip.io**: `myapp.192.168.1.100.sslip.io` resolves to `192.168.1.100`
- **dnsmasq**: Configure local wildcard DNS

Example using nip.io for local testing:

```bash
hop3 domain set --app myapp myapp.127.0.0.1.nip.io
```

## SSL/TLS Certificates

### Automatic Certificates (Let's Encrypt)

Hop3 uses pluggable TLS issuance engines. When the certbot engine is configured on the server (`ACME_ENGINE=certbot` with `ACME_EMAIL` set) and you bind a valid public domain, Hop3 automatically:

1. Requests a certificate from Let's Encrypt via certbot's webroot challenge
2. Configures the reverse proxy to use HTTPS
3. Sets up automatic certificate renewal
4. Redirects HTTP traffic to HTTPS

If the certbot engine cannot issue a certificate for a public domain, issuance fails loudly rather than silently falling back to a self-signed certificate. When no ACME engine is configured, Hop3 issues a self-signed certificate instead (see below).

### Certificate Requirements

For automatic certificates to work:

- Domain must resolve to your Hop3 server's public IP
- Port 80 must be accessible (for ACME HTTP-01 challenge)
- Domain must not be a local/private address

### Self-Signed Certificates

For internal or development deployments where Let's Encrypt isn't available, Hop3 uses self-signed certificates. This happens automatically when:

- Using the special `_` (underscore) hostname
- Using local/private IP addresses
- Let's Encrypt requests fail

### Certificate Status

Check certificate status:

```bash
# View app status (includes the app's URL)
hop3 app status --app myapp

# Check certificate files directly on the server (per-app cert/key)
ls /home/hop3/nginx/myapp.crt /home/hop3/nginx/myapp.key
```

## Special Hostname Values

### Catch-All (`_`)

Use the underscore hostname to create a catch-all application that responds to any hostname not matched by other apps:

```bash
hop3 domain set --app myapp _
```

The catch-all `_` must be the sole hostname — it cannot be combined with other domains.

This is useful for:

- Default landing pages
- Development environments
- Applications that handle their own routing

**Note**: Catch-all apps receive self-signed certificates (browsers will show warnings).

### Empty/Unset

If no hostnames are set (`HOST_NAME` empty or unset):

- No reverse proxy configuration is created
- App is only accessible via direct port
- No SSL certificate is provisioned

This is appropriate for:

- Internal microservices
- Background workers
- Apps behind a separate load balancer

## Reverse Proxy Backends

Hop3 supports multiple reverse proxy backends. The configuration syntax is the same regardless of which proxy you use.

| Proxy | Configuration File Location | Notes |
|-------|----------------------------|-------|
| Nginx | `/home/hop3/nginx/` | Default, most tested |
| Caddy | `/home/hop3/caddy/` | Automatic HTTPS |
| Traefik | `/home/hop3/traefik/` | Container-native |

The proxy is selected during server installation. All proxies support:

- Multiple hostnames per app
- Automatic SSL via Let's Encrypt
- HTTP to HTTPS redirection
- WebSocket proxying

## Troubleshooting

### Domain Not Resolving

1. Verify DNS propagation:
   ```bash
   dig myapp.example.com
   nslookup myapp.example.com
   ```

2. Check that DNS points to correct IP:
   ```bash
   curl -I http://myapp.example.com
   ```

3. Ensure the hostnames are set correctly:
   ```bash
   hop3 domain list --app myapp
   ```

### SSL Certificate Issues

1. Check certificate status:
   ```bash
   echo | openssl s_client -connect myapp.example.com:443 2>/dev/null | openssl x509 -noout -dates
   ```

2. Review the server's health and TLS engine:
   ```bash
   hop3 system status   # includes a Certificates section
   hop3 system info     # shows the TLS engine in effect
   ```

3. Review certbot's logs on the server (Hop3 invokes certbot with its own
   directories under `/home/hop3/certbot/`):
   ```bash
   sudo tail -n 50 /home/hop3/certbot/logs/letsencrypt.log
   ```

### Proxy Not Updating

After changing an app's hostnames:

1. Redeploy the application (a hostname change affects the proxy config, so a
   restart alone is not enough):
   ```bash
   hop3 deploy --app myapp
   ```

2. If issues persist, reload the proxy:
   ```bash
   # On the server
   sudo systemctl reload nginx  # or caddy/traefik
   ```

### Multiple Apps, Same Domain

Only one app can use a specific hostname. If you get errors about duplicate hostnames:

1. List all apps, then inspect the domains of a candidate:
   ```bash
   hop3 app list
   hop3 domain list --app other-app
   ```

2. Remove the conflicting hostname from the other app:
   ```bash
   hop3 domain remove --app other-app www.example.com
   hop3 deploy --app other-app
   ```

## Examples

### Production Setup with www Redirect

```bash
# Configure both domains
hop3 domain set --app myapp example.com www.example.com
hop3 deploy --app myapp
```

### Staging Environment

```bash
# Use subdomain for staging
hop3 domain set --app myapp-staging staging.example.com
hop3 deploy --app myapp-staging
```

### Multi-Tenant Application

For applications that handle multiple customer domains:

```bash
# Set primary domain for the app
hop3 domain set --app myapp app.example.com

# Application code handles tenant routing via request headers
# Example: customers access customer1.app.example.com, customer2.app.example.com
```

Use wildcard DNS (`*.app.example.com`) and let your application handle tenant routing internally.

### Internal Service (No Public Access)

```bash
# Don't set any hostname - app accessible only via its port
hop3 app start --app internal-api

# Look up the assigned port
hop3 app status --app internal-api
```

## Best Practices

1. **Always use HTTPS in production**: Bind a real public hostname to enable automatic SSL.

2. **Use descriptive subdomains**: `api.example.com`, `admin.example.com`, `staging.example.com` make it clear what each service does.

3. **Keep www redirects**: If you use `example.com`, also include `www.example.com` to handle both.

4. **Test DNS before deploying**: Verify DNS propagation before configuring the hostname in Hop3.

5. **Monitor certificate expiry**: While Hop3 handles renewal, monitor for failures in production.

## Related Guides

- [User Guide](user-guide.md) - General application deployment
- [Configuration Reference](../reference/config.md) - hop3.toml options
- [Administration Guide](administration.md) - Server-level configuration
