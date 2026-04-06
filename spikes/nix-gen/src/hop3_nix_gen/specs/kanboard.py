"""Kanboard: Kanban project management, PHP built-in server, MySQL."""

from hop3_nix_gen.spec import AppSpec, Source

SPEC = AppSpec(
    pname="kanboard",
    version="1.2.37",
    description="Kanban project management platform",
    template="php-app",
    php_version="php82",
    php_extensions=[
        "mysqli",
        "pdo_mysql",
        "pdo_sqlite",
        "gd",
        "mbstring",
        "xml",
        "curl",
        "zip",
        "ldap",
    ],
    source=Source(
        url="https://github.com/kanboard/kanboard/archive/refs/tags/v${version}.tar.gz",
        sha256="TVOLDXS3rX4n4cMQiztpkwmkYAbkTDhagD2+wZ+Erv8=",
        archive="tar-gz",
    ),
    strip_components=1,
    serve_mode="builtin",
    post_install_dirs=["data"],
    extra_paths=["${php}/bin"],
)
