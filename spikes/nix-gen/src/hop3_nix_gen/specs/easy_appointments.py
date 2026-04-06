"""Easy!Appointments: appointment scheduling, PHP + composer, MySQL."""

from hop3_nix_gen.spec import AppSpec, Source

SPEC = AppSpec(
    pname="easy-appointments",
    version="1.5.0",
    description="Open source appointment scheduling",
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
    ],
    needs_composer=True,
    source=Source(
        url="https://github.com/alextselegidis/easyappointments/archive/refs/tags/${version}.tar.gz",
        sha256="Skz6uMjvtiXaw34st/FxtTljycI4yAyYiqa6qr0Av3I=",
        archive="tar-gz",
    ),
    strip_components=1,
    serve_mode="builtin",
    runtime_env={
        "APP_URL": "http://localhost:8080",
    },
    extra_paths=["${php}/bin"],
)
