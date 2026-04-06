"""Dolibarr: ERP/CRM, PHP built-in server with htdocs webroot, composer, PostgreSQL."""

from hop3_nix_gen.spec import AppSpec, Source

SPEC = AppSpec(
    pname="dolibarr",
    version="19.0.3",
    description="Open source ERP and CRM for small and medium businesses",
    template="php-app",
    php_version="php82",
    php_extensions=[
        "pgsql",
        "pdo_pgsql",
        "gd",
        "mbstring",
        "xml",
        "curl",
        "zip",
        "intl",
        "calendar",
        "imap",
        "ldap",
    ],
    needs_composer=True,
    source=Source(
        url="https://github.com/Dolibarr/dolibarr/archive/refs/tags/${version}.tar.gz",
        sha256="UvzqWjVPhoj6Moq/+qGWv5BW9UUWTNf+iC0bt95lQWM=",
        archive="tar-gz",
    ),
    strip_components=1,
    serve_mode="builtin",
    web_root="htdocs",
    post_install_dirs=["documents"],
    runtime_env={
        "DOLI_ADMIN_LOGIN": "admin",
    },
    extra_paths=["${php}/bin"],
)
