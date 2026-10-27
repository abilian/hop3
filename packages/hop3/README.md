# hop3

Hop3 is a distribution for web applications: it deploys and runs them on your own server.

This package installs the `hop3` command, the client you deploy and manage apps with. It holds no code of its own: it installs [hop3-cli](https://pypi.org/project/hop3-cli/).

```bash
uv tool install hop3
hop3 --help
```

The server is a separate install, run as root on the machine that will host the apps:

```bash
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
```

Documentation: <https://hop3.cloud>

Releases 0.1 to 0.2 of this name were an earlier, unrelated server, and are yanked.
