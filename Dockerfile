FROM python:3.12

WORKDIR /app

RUN adduser hop3
RUN chown -R hop3:hop3 .

COPY pyproject.toml .
COPY uv.lock .
COPY README.md .
COPY packages packages

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
RUN cp /root/.local/bin/uv /usr/local/bin/uv

# Install uv dependencies and build
RUN uv sync

USER hop3

CMD ["echo", "OK"]
