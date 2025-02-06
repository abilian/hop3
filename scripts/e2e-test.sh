git clone https://github.com/abilian/hop3.git
cd hop3

apt-get update
apt-get install -y \
    software-properties-common build-essential make gcc g++ python3-dev python3-pip python3-wheel libpq-dev libffi-dev libsqlite3-dev libbz2-dev rsync npm ruby-rubygems bundler ruby-dev buildah docker-buildx

pip install --break-system-packages -U uv nox
uv sync
export HOP3_DEV_HOST=ssh.hop-dev.abilian.com
export HOP3_TEST_DOMAIN=hop-dev.abilian.com
ssh -o StrictHostKeyChecking=accept-new root@$HOP3_DEV_HOST 'echo hello'
git config --global init.defaultBranch main
git config --global user.email "you@example.com"
git config --global user.name "Your Name"
uv run make test-e2e
