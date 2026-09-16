<?php
// Minimal PHP app, deployed with no Procfile and no hop3.toml: the toolchain
// accepts on this file's existence and the runtime supplies the web worker.
// That is the property under test — a PHP app should need neither.
//
// `php_sapi_name()` is the assertion that matters. It answers "fpm-fcgi" when
// a php-fpm pool served the request and "cli-server" under `php -S`, so it
// distinguishes the production runtime from the development one by asking the
// interpreter rather than by inferring it from a status code.

$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH);

header('Content-Type: text/html; charset=utf-8');
?>
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>php-fpm hello</title>
<link rel="stylesheet" href="/assets/style.css"></head>
<body>
<h1>Hello from PHP</h1>
<p id="sapi">sapi: <?= htmlspecialchars(php_sapi_name(), ENT_QUOTES) ?></p>
<p id="routed">front controller handled: <?= htmlspecialchars($path, ENT_QUOTES) ?></p>
</body>
</html>
