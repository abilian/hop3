# Domain and Hostname Configuration

This guide explains how to configure custom domains, subdomains, and SSL certificates for your Hop3 applications.

## Overview

Hop3 uses the `HOST_NAME` environment variable to configure the domain(s) your application responds to. When set, Hop3 automatically:

1. Configures the reverse proxy (Nginx/Caddy/Traefik) with appropriate virtual host settings
2. Requests and manages SSL/TLS certificates via Let's Encrypt
3. Sets up HTTP to HTTPS redirection

## Quick Start

Set a custom domain for your app:

```bash
# Set the hostname
hop3 config set myapp HOST_NAME=myapp.example.com

# Restart to apply changes
hop3 app restart myapp
```

Your app is now accessible at `https://myapp.example.com` (assuming DNS is configured).

## Configuration Options

### Single Domain

```bash
hop3 config set myapp HOST_NAME=myapp.example.com
```

### Multiple Domains

Use comma-separated values to serve multiple domains:

```bash
hop3 config set myapp HOST_NAME=myapp.example.com,www.myapp.example.com
```

Both domains will point to the same application with the same SSL certificate.

### Using hop3.toml

You can also configure the hostname in your application's `hop3.toml`:

```toml
[env]
HOST_NAME = "myapp.example.com"
```

Or for multiple domains:

```toml
[env]
HOST_NAME = "myapp.example.com,www.myapp.example.com"
```

### No Domain (Direct Port Access)

If you don't set `HOST_NAME`, your app won't get a reverse proxy configuration. It will only be accessible via its direct port (useful for internal services):

```bash
# Check the assigned port
hop3 app status myapp
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
hop3 config set myapp HOST_NAME=myapp.127.0.0.1.nip.io
```

## SSL/TLS Certificates

### Automatic Certificates (Let's Encrypt)

When you set a `HOST_NAME` with a valid public domain, Hop3 automatically:

1. Requests a certificate from Let's Encrypt via certbot
2. Configures the reverse proxy to use HTTPS
3. Sets up automatic certificate renewal
4. Redirects HTTP traffic to HTTPS

No additional configuration is required.

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
# View app configuration including SSL info
hop3 app status myapp

# Check certificate files directly on the server
ls /home/hop3/nginx/certs/
```

## Special Hostname Values

### Catch-All (`_`)

Use the underscore hostname to create a catch-all application that responds to any hostname not matched by other apps:

```bash
hop3 config set myapp HOST_NAME=_
```

This is useful for:

- Default landing pages
- Development environments
- Applications that handle their own routing

**Note**: Catch-all apps receive self-signed certificates (browsers will show warnings).

### Empty/Unset

If `HOST_NAME` is empty or unset:

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

3. Ensure HOST_NAME is set correctly:
   ```bash
   hop3 config show myapp | grep HOST_NAME
   ```

### SSL Certificate Issues

1. Check certificate status:
   ```bash
   echo | openssl s_client -connect myapp.example.com:443 2>/dev/null | openssl x509 -noout -dates
   ```

2. Review certbot logs on the server:
   ```bash
   sudo journalctl -u certbot
   ```

3. Manually test certificate request:
   ```bash
   sudo certbot certonly --dry-run -d myapp.example.com
   ```

### Proxy Not Updating

After changing HOST_NAME:

1. Restart the application:
   ```bash
   hop3 app restart myapp
   ```

2. If issues persist, reload the proxy:
   ```bash
   # On the server
   sudo systemctl reload nginx  # or caddy/traefik
   ```

### Multiple Apps, Same Domain

Only one app can use a specific hostname. If you get errors about duplicate hostnames:

1. List all apps and their hostnames:
   ```bash
   hop3 apps
   ```

2. Remove the hostname from the conflicting app:
   ```bash
   hop3 config unset other-app HOST_NAME
   hop3 app restart other-app
   ```

## Examples

### Production Setup with www Redirect

```bash
# Configure both domains
hop3 config set myapp HOST_NAME=example.com,www.example.com
hop3 app restart myapp
```

### Staging Environment

```bash
# Use subdomain for staging
hop3 config set myapp-staging HOST_NAME=staging.example.com
hop3 app restart myapp-staging
```

### Multi-Tenant Application

For applications that handle multiple customer domains:

```bash
# Set primary domain for the app
hop3 config set myapp HOST_NAME=app.example.com

# Application code handles tenant routing via request headers
# Example: customers access customer1.app.example.com, customer2.app.example.com
```

Use wildcard DNS (`*.app.example.com`) and let your application handle tenant routing internally.

### Internal Service (No Public Access)

```bash
# Don't set HOST_NAME - app accessible only via port
hop3 app start internal-api

# Access via port
curl http://localhost:$(hop3 config get internal-api PORT)
```

## Best Practices

1. **Always use HTTPS in production**: Set a proper `HOST_NAME` to enable automatic SSL.

2. **Use descriptive subdomains**: `api.example.com`, `admin.example.com`, `staging.example.com` make it clear what each service does.

3. **Keep www redirects**: If you use `example.com`, also include `www.example.com` to handle both.

4. **Test DNS before deploying**: Verify DNS propagation before configuring the hostname in Hop3.

5. **Monitor certificate expiry**: While Hop3 handles renewal, monitor for failures in production.

## Related Guides

- [User Guide](user-guide.md) - General application deployment
- [Configuration Reference](../reference/config.md) - hop3.toml options
- [Administration Guide](administration.md) - Server-level configuration
