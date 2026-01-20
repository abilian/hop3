# Setting Up Nix on Ubuntu

This documents how to set up a working Nix environment on Ubuntu for Hop3 development.

## Install Nix

Install the `nix-bin` package:

```bash
sudo apt install nix-bin
```

Verify installation:

```bash
nix --version
# Expected: nix (Nix) 2.18.1 or similar
```

## Create a Dedicated User (Recommended)

Create a user for Nix operations:

```bash
sudo useradd -m -s /bin/bash hop3-nix
```

Give this user ownership of the Nix store:

```bash
sudo chown -R hop3-nix:hop3-nix /nix
```

## Enable Flakes

Flakes are the modern way to manage Nix projects. Enable them system-wide:

```bash
sudo mkdir -p /etc/nix
sudo sh -c 'echo "experimental-features = nix-command flakes" > /etc/nix/nix.conf'
```

## Configure User Environment

**Important**: When switching to the `hop3-nix` user, use a full login shell to get a clean environment:

```bash
sudo -i -u hop3-nix
```

If you use `su` or `sudo -u` instead, you may inherit environment variables from root that cause permission errors.

The user needs proper XDG environment variables. Add to `~/.profile` or `~/.bashrc`:

```bash
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_CACHE_HOME="$HOME/.cache"
export XDG_STATE_HOME="$HOME/.local/state"
```

## Verify Setup

Test that everything works:

```bash
nix run nixpkgs#hello
# Expected output: Hello, world!
```

Other useful test commands:

```bash
# Open a shell with Python available
nix shell nixpkgs#python3 --command python3 --version

# Search for packages
nix search nixpkgs python
```

## Common Issues

### "experimental Nix feature 'nix-command' is disabled"

The flakes config isn't being read. Ensure `/etc/nix/nix.conf` contains:
```
experimental-features = nix-command flakes
```

### "Permission denied" on /nix/store

The user doesn't own `/nix`. Fix with:
```bash
sudo chown -R hop3-nix:hop3-nix /nix
```

### "getting status of /root/.config/nix/..." Permission denied

You're running as a non-root user but inherited root's environment. Use a full login shell:
```bash
sudo -i -u hop3-nix
```

Or set XDG variables explicitly (see above).

## Key Nix Commands

| Command | Purpose |
|---------|---------|
| `nix run nixpkgs#<pkg>` | Run a package without installing |
| `nix shell nixpkgs#<pkg>` | Open shell with package available |
| `nix search nixpkgs <term>` | Search for packages |
| `nix profile install nixpkgs#<pkg>` | Install to user profile |
| `nix develop` | Enter a flake's dev shell |
| `nix build` | Build a flake's default package |
| `nix flake show` | Show outputs of a flake |
