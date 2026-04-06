"""BookStack: Laravel wiki, composer build, artisan serve, MySQL."""

from hop3_nix_gen.spec import AppSpec, Source

SPEC = AppSpec(
    pname="bookstack",
    version="24.02",
    description="Simple, self-hosted documentation platform",
    template="php-app",
    php_version="php82",
    php_extensions=[
        "mysqli",
        "pdo_mysql",
        "gd",
        "mbstring",
        "xml",
        "curl",
        "zip",
        "tokenizer",
        "bcmath",
        "intl",
        "ldap",
    ],
    needs_composer=True,
    source=Source(
        url="https://github.com/BookStackApp/BookStack/archive/refs/tags/v${version}.tar.gz",
        sha256="CDJ0X2x274ohrevyH+9w4J/wY9SEpdJTNO2MA0resLI=",
        archive="tar-gz",
    ),
    strip_components=1,
    serve_mode="artisan",
    post_install_dirs=[
        "storage/app",
        "storage/framework/cache",
        "storage/framework/sessions",
        "storage/framework/views",
        "storage/logs",
        "bootstrap/cache",
    ],
    runtime_env={
        "APP_ENV": "production",
        "APP_DEBUG": "false",
    },
    extra_paths=["${php}/bin"],
)
