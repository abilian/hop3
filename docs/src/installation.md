# Hop3 Installer Guide

This guide provides instructions on how to use the Hop3 installer script to set up the Hop3 environment on a server. The installer is designed to automate the installation and configuration process, making it easy to deploy Hop3 on any compatible system.

## Prerequisites

- A server running a Debian-based distribution (Debian, Ubuntu, etc.)
- Root access to the server via SSH
- Basic familiarity with terminal and command-line operations

## Installation Steps

1. Checkout the Hop3 sources on your workstation

1. Provision a server with Ubuntu 22.04 LTS

> \[!WARNING\]
> The installation script doesn't support Ubuntu 24.04 LTS yet.

3. Run, under Bash or Sh:

```bash
TARGET_HOST=name.of.your.target.host # <- replace with your target host
poetry install
make clean
poetry build
poetry run pyinfra --user root ${TARGET_HOST} installer/install-hop.py
```

Or, if yousing the Fish shell:

```fish
set TARGET_HOST name.of.your.target.host # <- replace with your target host
poetry install
make clean
poetry build
poetry run pyinfra --user root {$TARGET_HOST} installer/install-hop.py
```

## Demo

[![asciicast](https://asciinema.org/a/EyYlupPqQvY2ET0vTVkVpN5t3.svg)](https://asciinema.org/a/EyYlupPqQvY2ET0vTVkVpN5t3)

## Post-Installation Steps

- **Run hop-server setup**: After installation, SSH into your server as the `hop3` user and run:

  ```bash
  hop-server setup
  ```

  This command will:
  - Create necessary directories
  - Configure the uWSGI emperor
  - Generate and save `HOP3_SECRET_KEY` to `/home/hop3/hop3-server.toml` (used for JWT token signing)

  After setup completes, restart the hop3 service to load the configuration:

  ```bash
  sudo systemctl restart hop3
  ```

  The generated `hop3-server.toml` file contains server-wide configuration. You can edit this file to customize other server settings.

- **Create the first admin user**: Before you can use Hop3, you need to create an admin user and configure your local CLI. The easiest way is to use the SSH-assisted bootstrap from your workstation:

  ```bash
  hop3 init --ssh root@your-server.com
  ```

  This command will:
  1. Connect to your server via SSH
  2. Prompt you for admin username, email, and password
  3. Create the admin user on the server
  4. Save the API token to your local `~/.config/hop3-cli/config.toml`

  Example session:
  ```
  $ hop3 init --ssh root@my-server.com

  Connecting to my-server.com...
  Server URL [https://my-server.com]:
  Admin username: admin
  Admin email: admin@company.com
  Admin password: ********
  Confirm password: ********

  Admin user 'admin' created successfully.
  Configuration saved to ~/.config/hop3-cli/config.toml

  You're all set! Try:
    hop3 apps           # List applications
    hop3 auth:whoami    # Check current user
  ```

  **Alternative: Manual setup** - If you prefer to set up manually, SSH into your server and run:

  ```bash
  ssh root@your-server.com
  hop-server admin:create admin admin@example.com
  # Enter password when prompted
  # Copy the displayed token
  ```

  Then configure your local CLI:

  ```bash
  hop3 settings set server https://your-server.com
  hop3 settings set token <paste-token-here>
  ```

  **For automation (CI/CD)**: Use non-interactive mode:

  ```bash
  echo "$ADMIN_PASSWORD" | hop3 init \
    --ssh deploy@my-server.com \
    --username admin \
    --email admin@company.com \
    --server https://my-server.com \
    --password-stdin \
    --yes
  ```

- **Configure Hop3**: You may need to perform additional configuration steps specific to your application or environment. Refer to the Hop3 documentation for detailed configuration options.

- **Deploy Your Application**: With Hop3 installed, you can now deploy your web applications. Follow the Hop3 deployment guide to learn how to prepare your application for deployment.

- **Secure Your Server**: Ensure your server is secured according to best practices. This includes setting up firewalls,
  securing SSH access, and regularly updating your system and applications.

## Troubleshooting

If you encounter issues during the installation, check the following:

- Ensure all prerequisites are met and your server meets the minimum requirements for Hop3.
- Review the output of the installer script for any error messages or warnings.
- Check the logs for `nginx`, `uwsgi`, and other services for specific error details.

## Support

For additional help or to report issues, please visit the Hop3 GitHub repository and open an issue, or consult the Hop3 community forums.
