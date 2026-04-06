"""LimeSurvey: survey platform, PHP + zip archive with wrapper dir, PostgreSQL."""

from hop3_nix_gen.spec import AppSpec, Source

SPEC = AppSpec(
    pname="limesurvey",
    version="6.16.10",
    description="Professional online survey and data collection tool",
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
        "ldap",
        "imap",
    ],
    source=Source(
        # The version encoding is specific to LimeSurvey's download format.
        url="https://download.limesurvey.org/latest-master/limesurvey${version}+260223.zip",
        sha256="jXRc89eWmPd354Zk2peRJR7v4G9ePwTJT9BS2es3tnk=",
        archive="zip",
    ),
    # The zip contains a top-level "limesurvey" directory. We cp from
    # that subdir instead of moving files around in the unpack phase.
    source_root="limesurvey",
    serve_mode="builtin",
    post_install_dirs=["tmp", "upload"],
    runtime_env={
        "ADMIN_USER": "admin",
        "ADMIN_NAME": "Administrator",
        "ADMIN_EMAIL": "admin@example.com",
    },
    extra_paths=["${php}/bin"],
)
