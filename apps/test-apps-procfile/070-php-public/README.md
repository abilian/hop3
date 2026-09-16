# 070-php-public

The front-controller-in-a-subdirectory layout (Laravel, Symfony), and the
containment that layout exists for.

`document_root()` resolves `public/` here, so what nginx serves is `public/`
and not the project root. The fixture asserts the consequence directly: the
`APP_KEY` canary in `.env`, one level above the document root, must not be
retrievable by any path. Serving the project root instead would publish `.env`,
`composer.json` and the whole vendor tree — which is why the detection is a
security default rather than a convenience.

It also carries a `[healthcheck].contains`, so the **deploy's own readiness
gate** has to assert page content for a FastCGI app. That check runs through
nginx, because a php-fpm pool speaks FastCGI and a pool child answers
`ping.path` just as healthily when the application is sitting on an install
wizard.
