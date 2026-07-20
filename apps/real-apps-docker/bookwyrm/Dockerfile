# BookWyrm Dockerfile for Hop3
# Django + PostgreSQL + Redis + Celery (worker started in-container)

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    libssl-dev \
    libffi-dev \
    build-essential \
    gettext \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash bookwyrm

WORKDIR /opt/bookwyrm

ARG BOOKWYRM_VERSION=0.8.5
RUN curl -fsSL "https://github.com/bookwyrm-social/bookwyrm/archive/refs/tags/v${BOOKWYRM_VERSION}.tar.gz" \
    | tar xz --strip-components=1

# BookWyrm pyproject uses PEP-735 [dependency-groups] with no
# [project].dependencies; pure-Python tomllib extraction is more
# robust than `uv pip compile`, which tries to build the project
# itself and fails on BookWyrm's polyglot top-level layout
# (`bookwyrm/`, `celerywyrm/`, `anubis/`, …) via setuptools auto-
# discovery. gunicorn isn't in the upstream deps — append for WSGI.
RUN python3 -c 'import tomllib, sys; \
data = tomllib.load(open("pyproject.toml", "rb")); \
deps = data.get("dependency-groups", {}).get("main", []); \
open("requirements.txt", "w").write("\n".join(d for d in deps if isinstance(d, str)) + "\ngunicorn\n")'

RUN python3 -m venv /opt/bookwyrm/venv \
    && /opt/bookwyrm/venv/bin/pip install --no-cache-dir -r requirements.txt

ENV PATH="/opt/bookwyrm/venv/bin:${PATH}"

RUN mkdir -p /data && chown -R bookwyrm:bookwyrm /opt/bookwyrm /data

COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
