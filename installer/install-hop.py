import glob

from pyinfra import host
from pyinfra.facts.files import File
from pyinfra.operations import server, files, apt, systemd, pip

PACKAGES = [
    "bc",
    "git",
    "sudo",
    "cron",
    "build-essential",
    "libpcre3-dev",
    "zlib1g-dev",
    # Python
    "python3",
    "python3-pip",
    "python3-click",
    "python3-dev",
    "python3-virtualenv",
    "python3-setuptools",
    # Nginx
    "nginx",
    "acl",
    # uwsgi
    "uwsgi-core",
    # For builders
    # - Ruby
    "ruby",
    "ruby-dev",
    "ruby-bundler",
    # - Nodejs
    "npm",
    # - Go
    "golang",
    # - Clojure
    "clojure",
    "leiningen",
    "uwsgi-plugin-python3",
    # - Nodejs
    "npm",
    "nodeenv",
]

HOP3_USER = "hop3"
SSH_USER = "root"
HOME_DIR = f"/home/{HOP3_USER}"
VENV = f"{HOME_DIR}/venv"
HOP_SCRIPT = f"{VENV}/bin/hop-agent"


def main():
    setup_server()
    setup_hop3()
    setup_uwsgi()
    setup_acme()
    setup_nginx()


def setup_server():
    server.user(
        name="Add hop3 user",
        user=HOP3_USER,
        home=HOME_DIR,
        shell="/bin/bash",
        group="www-data",
    )

    apt.packages(
        name="Install Debian Packages",
        packages=PACKAGES,
        update=True,
    )


def setup_hop3():
    src_file = glob.glob("dist/hop3-*.tar.gz")[0]

    files.put(
        name="Put hop3 source package",
        src=src_file,
        dest=f"{HOME_DIR}/tmp/hop3.tar.gz",
        mode="0700",
        _su_user=HOP3_USER,
    )

    pip.virtualenv(
        name="Create a virtualenv for hop3",
        path=VENV,
        _su_user=HOP3_USER,
    )

    pip.packages(
        name="Install hop3",
        packages=f"{HOME_DIR}/tmp/hop3.tar.gz",
        virtualenv=VENV,
        _su_user=HOP3_USER,
    )

    server.shell(
        name="Run hop3 setup",
        commands=[f"{HOP_SCRIPT} setup"],
        _su_user=HOP3_USER,
    )

    server.shell(
        name="Save root's authorized_keys",
        commands=[
            "cat /root/.ssh/authorized_keys > /tmp/root_authorized_keys",
            f"chown {HOP3_USER} /tmp/root_authorized_keys",
        ],
    )

    server.shell(
        name="Use root's SSH keys",
        commands=[
            f"{HOP_SCRIPT} setup:ssh /tmp/root_authorized_keys",
            "rm /tmp/root_authorized_keys",
        ],
        _su_user=HOP3_USER,
    )


def setup_uwsgi():
    files.link(
        name="Create uwsgi symlink",
        path="/usr/local/bin/uwsgi-hop3",
        target="/usr/bin/uwsgi",
    )

    files.put(
        name="Install uwsgi-hop3 systemd script",
        src="etc/uwsgi-hop3.service",
        dest="/etc/systemd/system/uwsgi-hop3.service",
        mode="0600",
    )

    systemd.service(
        name="Enable and start uwsgi-hop3 service",
        service="uwsgi-hop3",
        enabled=True,
    )


def setup_acme():
    acme_sh_exists = host.get_fact(File, f"{HOME_DIR}/.acme.sh/acme.sh")

    if not acme_sh_exists:
        files.download(
            name="Download acme.sh",
            src="https://raw.githubusercontent.com/Neilpang/acme.sh/master/acme.sh",
            dest=f"{HOME_DIR}/acme.sh",
            mode="0755",
            _su_user=HOP3_USER,
        )

        server.shell(
            name="Execute acme.sh installer",
            commands=[f"bash {HOME_DIR}/acme.sh --install"],
            _su_user=HOP3_USER,
            _chdir=HOME_DIR,
        )

        files.file(
            name="Remove acme.sh installer",
            path=f"{HOME_DIR}/acme.sh",
            present=False,
            _su_user=HOP3_USER,
        )

    server.shell(
        name="Run a manual upgrade",
        commands=[f"bash {HOME_DIR}/.acme.sh/acme.sh --upgrade"],
        _su_user=HOP3_USER,
    )

    server.shell(
        name="Set default CA to letsencrypt",
        commands=[
            f"bash {HOME_DIR}/.acme.sh/acme.sh --set-default-ca --server letsencrypt"
        ],
        _su_user=HOP3_USER,
    )

    files.line(
        name="Configure acme.sh to auto-upgrade",
        path=f"{HOME_DIR}/.acme.sh/account.conf",
        line="^#AUTO_UPGRADE=",
        replace='AUTO_UPGRADE="1"',
        _su_user=HOP3_USER,
    )


def setup_nginx():
    files.put(
        name="Get nginx default config",
        src="etc/nginx.default.dist",
        dest="/etc/nginx/sites-available/default",
        force=True,
    )

    files.put(
        name="Get systemd.path hop3-nginx.path",
        src="etc/hop3-nginx.path",
        dest="/etc/systemd/system/hop3-nginx.path",
    )

    files.put(
        name="Get systemd.path hop3-nginx.service",
        src="etc/hop3-nginx.service",
        dest="/etc/systemd/system/hop3-nginx.service",
    )

    systemd.service(
        name="Restart nginx service",
        service="nginx",
        enabled=True,
        restarted=True,
    )

    systemd.service(
        name="Start hop3-nginx.path",
        service="hop3-nginx.path",
        enabled=True,
    )


main()
