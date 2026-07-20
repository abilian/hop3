# Stirling-PDF Dockerfile for Hop3
# Local web PDF toolkit — built from debian:trixie-slim + OpenJDK

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

# Minimal install: only the JRE and retrieval tools. The optional
# LibreOffice / OCR / qpdf / poppler packs are BIG (~1 GB combined)
# and gate specific features (office conversion, OCR, etc). Leave them
# out of the baseline image; add them explicitly if those features are
# needed.
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    curl \
    ca-certificates \
    openjdk-21-jre-headless \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash stirling

ARG STIRLING_PDF_VERSION=v2.9.2
RUN curl -fsSL "https://github.com/Stirling-Tools/Stirling-PDF/releases/download/${STIRLING_PDF_VERSION}/Stirling-PDF.jar" \
    -o /opt/Stirling-PDF.jar

COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
