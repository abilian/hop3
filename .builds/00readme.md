# Build profiles for Sourcehut builds

By default, all the builds are against the "latest" version of the dependencies ("stable" for Debian).

For Ubuntu (and maybe others in the future), additionally, we support the latest LTS version. (NB: this is currently irrelevant, as the LTS is also the latest release.)

See https://builds.sr.ht/~sfermigier for the latest build statuses.

TODO: fix all builds.

NB: we'd like to run CI against all the possible Linux distributions available on Sourcehut, but we're limited to 4.

So we're focusing on: Ubuntu, Debian, Fedora, and Rocky Linux for now.


## Memento

Here is a brief description of the packaging situation for each of the (potentially) supported operating systems and distributions:

### Alpine Linux
**Package Manager:** `apk`
- **Searching for Packages:** Use `apk search <package_name>`
- **Installing Packages:** Use `apk add <package_name>`

### Arch Linux
**Package Manager:** `pacman`
- **Searching for Packages:** Use `pacman -Ss <package_name>`
- **Installing Packages:** Use `pacman -S <package_name>`

### Debian & Ubuntu
**Package Manager:** `apt`
- **Searching for Packages:** Use `apt search <package_name>`
- **Installing Packages:** Use `apt install <package_name>`

### Fedora & Rocky Linux
**Package Manager:** `dnf`
- **Searching for Packages:** Use `dnf search <package_name>`
- **Installing Packages:** Use `dnf install <package_name>`

### FreeBSD
**Package Manager:** `pkg`
- **Searching for Packages:** Use `pkg search <package_name>`
- **Installing Packages:** Use `pkg install <package_name>`

### Guix
**Package Manager:** `guix`
- **Searching for Packages:** Use `guix search <package_name>`
- **Installing Packages:** Use `guix install <package_name>`

### NetBSD
**Package Manager:** `pkgin` (part of the pkgsrc framework)
- **Searching for Packages:** Use `pkgin search <package_name>`
- **Installing Packages:** Use `pkgin install <package_name>`

### NixOS
**Package Manager:** `nix`
Thank you for pointing that out. Here is the correct way to search for and install packages on NixOS using the `nix` package manager:

### NixOS
**Package Manager:** `nix`
- **Searching for Packages:** Use `nix search <package_name>`
- **Installing Packages:** Use `nix-env -i <package_name>`

### OpenBSD
**Package Manager:** `pkg_add` and `pkg_info`
- **Searching for Packages:** Use `pkg_info -Q <package_name>`
- **Installing Packages:** Use `pkg_add <package_name>`
