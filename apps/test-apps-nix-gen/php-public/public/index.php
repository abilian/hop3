<?php
// Front controller in a subdirectory, the Laravel / Symfony layout. The point
// of the fixture is what is NOT reachable: everything beside this directory.
header('Content-Type: text/html; charset=utf-8');
?>
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>php-fpm public root</title></head>
<body>
<h1>Served from public/</h1>
<p id="sapi">sapi: <?= htmlspecialchars(php_sapi_name(), ENT_QUOTES) ?></p>
</body>
</html>
