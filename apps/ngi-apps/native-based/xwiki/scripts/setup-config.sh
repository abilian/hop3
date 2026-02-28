#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# Configure PostgreSQL in hibernate.cfg.xml
if [ -f webapps/xwiki/WEB-INF/hibernate.cfg.xml ]; then
    # Backup original
    cp webapps/xwiki/WEB-INF/hibernate.cfg.xml webapps/xwiki/WEB-INF/hibernate.cfg.xml.bak

    # Configure for PostgreSQL
    cat > webapps/xwiki/WEB-INF/hibernate.cfg.xml << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE hibernate-configuration PUBLIC
  "-//Hibernate/Hibernate Configuration DTD//EN"
  "http://www.hibernate.org/dtd/hibernate-configuration-3.0.dtd">
<hibernate-configuration>
  <session-factory>
    <property name="connection.url">jdbc:postgresql://${PGHOST:-localhost}:${PGPORT:-5432}/${PGDATABASE:-xwiki}</property>
    <property name="connection.username">${PGUSER:-xwiki}</property>
    <property name="connection.password">${PGPASSWORD:-}</property>
    <property name="connection.driver_class">org.postgresql.Driver</property>
    <property name="dialect">org.hibernate.dialect.PostgreSQLDialect</property>
    <property name="dbcp.poolPreparedStatements">true</property>
    <property name="dbcp.maxOpenPreparedStatements">20</property>
    <mapping resource="xwiki.hbm.xml"/>
    <mapping resource="feeds.hbm.xml"/>
    <mapping resource="instance.hbm.xml"/>
    <mapping resource="notification-filter-preferences.hbm.xml"/>
    <mapping resource="mailsender.hbm.xml"/>
  </session-factory>
</hibernate-configuration>
EOF
fi

# Configure Jetty port
if [ -n "$PORT" ] && [ -f start_xwiki.sh ]; then
    sed -i "s/8080/${PORT}/g" start_xwiki.sh
fi

echo "XWiki configuration ready"
