# 060-php-hello

A PHP app with **no Procfile and no hop3.toml**. The PHP toolchain accepts on
`index.php`, and the php-fpm runtime supplies the web worker — a PHP app should
need neither file, and this fixture fails if that stops being true.

What it pins:

- `php_sapi_name()` is `fpm-fcgi`, so a php-fpm pool served the request. Under
  the old `php -S` start line it would read `cli-server`.
- An unrouted path reaches the front controller through nginx's `try_files`.
- A static asset is served off disk by nginx (as `www-data`, via the `hop3`
  group) without touching the interpreter.

See `070-php-public` for the front-controller-in-a-subdirectory case and the
document-root containment it exists to guarantee.
