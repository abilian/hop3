"""Invoice Ninja: Laravel + composer with --ignore-platform-reqs, nodejs, MySQL."""

from hop3_nix_gen.spec import AppSpec, Source

SPEC = AppSpec(
    pname="invoice-ninja",
    version="5.8.37",
    description="Free open-source invoicing platform",
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
        "bcmath",
        "intl",
        "soap",
        "fileinfo",
        "tokenizer",
    ],
    needs_composer=True,
    composer_extra_flags=["--ignore-platform-reqs"],
    extra_native_build_inputs=["pkgs.nodejs"],
    source=Source(
        url="https://github.com/invoiceninja/invoiceninja/archive/refs/tags/v${version}.tar.gz",
        sha256="7NZs3hAxH3awKMeIlwqem6gnVCRGdpDvZZ+7SW033qY=",
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
        "public/storage",
    ],
    runtime_env={
        "APP_ENV": "production",
        "APP_DEBUG": "false",
    },
    extra_paths=["${php}/bin"],
)
