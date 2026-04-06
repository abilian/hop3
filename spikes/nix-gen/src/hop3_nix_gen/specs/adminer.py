"""Adminer: single PHP file, serves with PHP built-in server."""

from hop3_nix_gen.spec import AppSpec, Source

SPEC = AppSpec(
    pname="adminer",
    version="4.8.1",
    description="Database management in a single PHP file",
    template="php-app",
    php_version="php82",
    php_extensions=[
        "mysqli",
        "pgsql",
        "pdo_mysql",
        "pdo_pgsql",
        "pdo_sqlite",
    ],
    source=Source(
        url="https://github.com/vrana/adminer/releases/download/v${version}/adminer-${version}.php",
        sha256="L9fm2PmHskOrGDkklVH2KtzhlwTEfT0MjdnlfqW5xrM=",
    ),
    single_file=True,
    serve_mode="builtin",
    extra_paths=["${php}/bin"],
)
