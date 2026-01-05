# DNS Configuration for Tutorial Testing

Tutorial tests require DNS wildcard resolution to work. Each deployed application gets a unique hostname like `hop3-tuto-express.hop3.local`, which must resolve to the Hop3 server IP.

## Quick Setup (macOS)

Run the provided setup script:

```bash
# Replace <server-ip> with your Hop3 server IP
python scripts/setup-dnsmasq.py <server-ip>
```

This configures:
- `*.hop3.local` -> `<server-ip>` (for remote SSH testing)
- `*.hop3-docker.local` -> `127.0.0.1` (for Docker testing)

## Manual Setup

### Prerequisites

Install dnsmasq on macOS:

```bash
brew install dnsmasq
```

### Configuration

1. **Create dnsmasq config** at `/opt/homebrew/etc/dnsmasq.d/hop3.conf`:

```conf
# Wildcard DNS for Hop3 testing
address=/hop3.local/<server-ip>
address=/hop3-docker.local/127.0.0.1
```

2. **Configure main dnsmasq.conf** at `/opt/homebrew/etc/dnsmasq.conf`:

```conf
# Listen on localhost
listen-address=127.0.0.1

# Include additional config files
conf-dir=/opt/homebrew/etc/dnsmasq.d/,*.conf
```

3. **Create macOS resolver files**:

```bash
sudo mkdir -p /etc/resolver

# For remote testing
echo "nameserver 127.0.0.1" | sudo tee /etc/resolver/hop3.local

# For Docker testing
echo "nameserver 127.0.0.1" | sudo tee /etc/resolver/hop3-docker.local
```

4. **Start dnsmasq**:

```bash
sudo dnsmasq
```

### Verify Configuration

```bash
# Test wildcard resolution
dig test.hop3.local @127.0.0.1

# Expected: resolves to your server IP
```

## Running Tutorial Tests

Once DNS is configured:

```bash
# For remote server testing (default)
python scripts/run-all-tutorials.py

# For Docker testing
HOP3_TEST_DOMAIN=hop3-docker.local python scripts/run-all-tutorials.py
```

## Troubleshooting

### DNS resolution fails

1. Check if dnsmasq is running:
   ```bash
   sudo lsof -i :53
   ```

2. Restart dnsmasq:
   ```bash
   sudo pkill dnsmasq
   sudo dnsmasq
   ```

3. Verify resolver files exist:
   ```bash
   ls -la /etc/resolver/
   ```

### After reboot

dnsmasq must be started manually:

```bash
sudo /opt/homebrew/opt/dnsmasq/sbin/dnsmasq
```

Or configure it to start at boot:

```bash
sudo brew services start dnsmasq
```

## Linux Setup

On Linux, you can use dnsmasq or NetworkManager:

### Using NetworkManager (Ubuntu/Debian)

1. Create `/etc/NetworkManager/dnsmasq.d/hop3.conf`:
   ```conf
   address=/hop3.local/<server-ip>
   ```

2. Enable dnsmasq in NetworkManager:
   ```bash
   sudo sed -i 's/#dns=dnsmasq/dns=dnsmasq/' /etc/NetworkManager/NetworkManager.conf
   sudo systemctl restart NetworkManager
   ```

### Using systemd-resolved

1. Create `/etc/systemd/resolved.conf.d/hop3.conf`:
   ```conf
   [Resolve]
   DNS=127.0.0.1
   Domains=~hop3.local
   ```

2. Add entry to `/etc/hosts`:
   ```
   <server-ip> *.hop3.local
   ```

Note: Linux wildcard DNS support varies by distribution. Testing with explicit hosts entries may be needed.
