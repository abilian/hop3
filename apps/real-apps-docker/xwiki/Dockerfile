# XWiki Dockerfile for Hop3
# Advanced enterprise wiki

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    openjdk-21-jre-headless \
    curl \
    ca-certificates \
    unzip \
    gettext-base \
    libpostgresql-jdbc-java \
    && rm -rf /var/lib/apt/lists/*

# Create xwiki user
RUN useradd -m -d /var/lib/xwiki -s /bin/bash xwiki

# Create directories
RUN mkdir -p /var/lib/xwiki/data /opt/xwiki \
    && chown -R xwiki:xwiki /var/lib/xwiki /opt/xwiki

WORKDIR /opt/xwiki

# Download XWiki from Maven repository (using jetty-hsqldb package, we'll override DB config)
ARG XWIKI_VERSION=16.1.0
RUN curl -fsSL "https://maven.xwiki.org/releases/org/xwiki/platform/xwiki-platform-distribution-jetty-hsqldb/${XWIKI_VERSION}/xwiki-platform-distribution-jetty-hsqldb-${XWIKI_VERSION}.zip" \
    -o /tmp/xwiki.zip \
    && unzip -q /tmp/xwiki.zip -d /opt \
    && mv /opt/xwiki-platform-distribution-jetty-hsqldb-${XWIKI_VERSION}/* /opt/xwiki/ \
    && rm /tmp/xwiki.zip \
    && chown -R xwiki:xwiki /opt/xwiki

# Copy PostgreSQL JDBC driver
RUN cp /usr/share/java/postgresql.jar /opt/xwiki/webapps/xwiki/WEB-INF/lib/

# Create hibernate config template for PostgreSQL
RUN echo '<?xml version="1.0" encoding="UTF-8"?>\n\
<!DOCTYPE hibernate-configuration PUBLIC\n\
  "-//Hibernate/Hibernate Configuration DTD//EN"\n\
  "http://www.hibernate.org/dtd/hibernate-configuration-3.0.dtd">\n\
<hibernate-configuration>\n\
  <session-factory>\n\
    <property name="hibernate.connection.url">jdbc:postgresql://${PGHOST}:${PGPORT}/${PGDATABASE}</property>\n\
    <property name="hibernate.connection.username">${PGUSER}</property>\n\
    <property name="hibernate.connection.password">${PGPASSWORD}</property>\n\
    <property name="hibernate.connection.driver_class">org.postgresql.Driver</property>\n\
    <property name="hibernate.dialect">org.hibernate.dialect.PostgreSQLDialect</property>\n\
    <property name="hibernate.connection.pool_size">2</property>\n\
    <property name="hibernate.hbm2ddl.auto">update</property>\n\
    <property name="hibernate.show_sql">false</property>\n\
    <mapping resource="xwiki.hbm.xml"/>\n\
    <mapping resource="feeds.hbm.xml"/>\n\
    <mapping resource="activitystream.hbm.xml"/>\n\
    <mapping resource="instance.hbm.xml"/>\n\
  </session-factory>\n\
</hibernate-configuration>\n\
' > /opt/xwiki/webapps/xwiki/WEB-INF/hibernate.cfg.xml.template

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment (PORT and PG* are required, no defaults)
ENV XWIKI_DATA_DIR=/var/lib/xwiki/data

# Data volume
VOLUME /var/lib/xwiki/data

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start.sh"]
