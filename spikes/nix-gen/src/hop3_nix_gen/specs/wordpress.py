"""WordPress: PHP built-in server, MySQL backend."""

from hop3_nix_gen.spec import AppSpec, Source

SPEC = AppSpec(
    pname="wordpress",
    version="6.4.2",
    description="Popular open source content management system",
    template="php-app",
    php_version="php82",
    php_extensions=[
        "mysqli",
        "pdo_mysql",
        "gd",
        "zip",
        "curl",
        "mbstring",
        "xml",
        "intl",
        "exif",
    ],
    source=Source(
        url="https://wordpress.org/wordpress-${version}.tar.gz",
        sha256="m4KJELf5zs3gwAQPmAhoPe2rhopZFsYN6OzAv6Wzo6c=",
        archive="tar-gz",
    ),
    strip_components=1,
    serve_mode="builtin",
    post_install_dirs=[
        "wp-content/uploads",
        "wp-content/plugins",
        "wp-content/themes",
    ],
    runtime_env={
        "WP_DEBUG": "false",
    },
    extra_paths=["${php}/bin"],
)
