# Notes on Hop3 config

(This will go into the documentation eventually.)

## Global config

The global configuration file is located at `~hop3/config.toml`.

It may be overridden by database settings, which are stored in the `hop3` database.

Example (not final, and not fully implemented yet):

```toml
[hop3]
# Default values
database_uri = "sqlite:///hop3.db"
log_level = "INFO"
log_format = "text"
log_file = "hop3.log"

[[hop3.backup]]
backend = "local"
path = "/home/hop3/backups"
period = "daily"
keep = 7

# There may be other backups, such as:
[[hop3.backup]]
backend = "s3"
bucket = "my-bucket"
path = "hop3"
period = "daily"
keep = 7

#


```


## Per-app config

Each app may have its own configuration file, located at `hop3/config.toml` or `hop3-config.toml` (looked up in that order).

Here's an example:

```toml
[metadata]
name = "my-app"
description = "My app description"
version = "0.1.0"
# ...

[env]
# These environment variables will be set when both building and running the app.
VAR1 = "value1"
VAR2 = "value2"
# ...

[build]
# Additional, hop3-specific, config for building the app

[run]
# Additional, hop3-specific, config for running the app.
```
