"""Nextcloud: self-hosted productivity, PHP + tar.bz2 archive, MySQL."""

from hop3_nix_gen.spec import AppSpec, Source

SPEC = AppSpec(
    pname="nextcloud",
    version="28.0.2",
    description="Self-hosted productivity platform",
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
        "intl",
        "bcmath",
        "gmp",
        "exif",
        "apcu",
        "opcache",
        "fileinfo",
    ],
    source=Source(
        url="https://download.nextcloud.com/server/releases/nextcloud-${version}.tar.bz2",
        sha256="3jTWuvPszqz90TjoVSDNheHSzmeY2f+keKwX6x76HQg=",
        archive="tar-bz2",
    ),
    strip_components=1,
    serve_mode="builtin",
    post_install_dirs=["data", "config"],
    extra_paths=["${php}/bin"],
)
