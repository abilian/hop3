# 155-flask-redis

Smoke test for the Hop3 Redis addon: declares `[[addons]] type = "redis"`, then
sets a key and reads it back through the injected credentials.

The sibling of `150-flask-s3`. It exists because nothing in the published
catalog declared a redis addon — only `alpha` entries did — so `--with redis`
provisioned a service that no test ever connected to. That gap hid a real bug:
the installer enabled and restarted Redis with bare `systemctl` under
`check=False`, so on a container it did nothing, said nothing, and left Redis
down. An app that talks to the addon is what turns that into a failing test.
