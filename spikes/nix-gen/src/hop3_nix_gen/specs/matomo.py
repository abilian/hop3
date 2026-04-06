"""Matomo: web analytics platform, PHP built-in server, MySQL."""

from hop3_nix_gen.spec import AppSpec, Source

SPEC = AppSpec(
    pname="matomo",
    version="5.0.1",
    description="Open source web analytics platform",
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
        "zlib",
        "intl",
    ],
    source=Source(
        url="https://builds.matomo.org/matomo-${version}.tar.gz",
        sha256="4dtIUinaEPtuEaangdlaIsw0xduG4AeUEaIUJ0IJ8Dw=",
        archive="tar-gz",
    ),
    strip_components=1,
    serve_mode="builtin",
    post_install_dirs=["tmp"],
    extra_paths=["${php}/bin"],
)
