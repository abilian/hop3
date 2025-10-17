# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

NGINX_TEMPLATE = """
$HOP3_INTERNAL_PROXY_CACHE_PATH
upstream $APP {
  server $NGINX_SOCKET;
}
server {
  listen $NGINX_IPV6_ADDRESS:80;
  listen $NGINX_IPV4_ADDRESS:80;

  location ^~ /.well-known/acme-challenge {
    allow all;
    root ${ACME_WWW};
  }
$HOP3_INTERNAL_NGINX_COMMON
}
"""

NGINX_HTTPS_ONLY_TEMPLATE = """
$HOP3_INTERNAL_PROXY_CACHE_PATH
upstream $APP {
  server $NGINX_SOCKET;
}
server {
  listen      $NGINX_IPV6_ADDRESS:80;
  listen      $NGINX_IPV4_ADDRESS:80;
  server_name $HOST_NAME;

  location ^~ /.well-known/acme-challenge {
    allow all;
    root ${ACME_WWW};
  }

  location / {
    return 301 https://$server_name$request_uri;
  }
}

server {
$HOP3_INTERNAL_NGINX_COMMON
}
"""

NGINX_COMMON_FRAGMENT = r"""
  listen              $NGINX_IPV6_ADDRESS:$NGINX_SSL;
  listen              $NGINX_IPV4_ADDRESS:$NGINX_SSL;
  ssl_certificate     $NGINX_ROOT/$APP.crt;
  ssl_certificate_key $NGINX_ROOT/$APP.key;
  server_name         $HOST_NAME;
  # These are not required under systemd - enable for debugging only
  # access_log        $LOG_ROOT/$APP/access.log;
  # error_log         $LOG_ROOT/$APP/error.log;

  # Enable gzip compression
  gzip on;
  gzip_proxied any;
  gzip_types text/plain text/xml text/css text/javascript text/js application/x-javascript application/javascript application/json application/xml+rss application/atom+xml image/svg+xml;
  gzip_comp_level 7;
  gzip_min_length 2048;
  gzip_vary on;
  gzip_disable "MSIE [1-6]\.(?!.*SV1)";
  # set a custom header for requests
  add_header X-Deployed-By Hop3;

  $HOP3_INTERNAL_NGINX_CUSTOM_CLAUSES
  $HOP3_INTERNAL_NGINX_STATIC_MAPPINGS
  $HOP3_INTERNAL_NGINX_CACHE_MAPPINGS
  $HOP3_INTERNAL_NGINX_BLOCK_GIT
  $HOP3_INTERNAL_NGINX_PORTMAP
"""

NGINX_PORTMAP_FRAGMENT = """
  location    / {
    $HOP3_INTERNAL_NGINX_UWSGI_SETTINGS
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Remote-Address $remote_addr;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Request-Start $msec;
    $NGINX_ACL
  }
"""

NGINX_ACME_FIRSTRUN_TEMPLATE = """
server {
  listen      $NGINX_IPV6_ADDRESS:80;
  listen      $NGINX_IPV4_ADDRESS:80;
  server_name $HOST_NAME;

  location ^~ /.well-known/acme-challenge {
    allow all;
    root ${ACME_WWW};
  }
}
"""

HOP3_INTERNAL_NGINX_STATIC_MAPPING = """
  location $static_url {
      sendfile on;
      sendfile_max_chunk 1m;
      tcp_nopush on;
      directio 8m;
      aio threads;
      root $static_path;
      try_files $uri $uri/index.html $uri.html =404;
  }
"""

HOP3_INTERNAL_PROXY_CACHE_PATH = """
uwsgi_cache_path $cache_path levels=1:2 keys_zone=$app:20m inactive=$cache_time_expiry max_size=$cache_size use_temp_path=off;
"""

HOP3_INTERNAL_NGINX_CACHE_MAPPING = """
    location ~* ^/($cache_prefixes) {
        uwsgi_cache $APP;
        uwsgi_cache_min_uses 1;
        uwsgi_cache_key $host$uri;
        uwsgi_cache_valid 200 304 $cache_time_content;
        uwsgi_cache_valid 301 307 $cache_time_redirects;
        uwsgi_cache_valid 500 502 503 504 0s;
        uwsgi_cache_valid any $cache_time_any;
        uwsgi_hide_header Cache-Control;
        add_header Cache-Control "public, max-age=$cache_time_control";
        add_header X-Cache $upstream_cache_status;
        $HOP3_INTERNAL_NGINX_UWSGI_SETTINGS
    }
"""

HOP3_INTERNAL_NGINX_UWSGI_SETTINGS = """
    uwsgi_pass $APP;
    uwsgi_param QUERY_STRING $query_string;
    uwsgi_param REQUEST_METHOD $request_method;
    uwsgi_param CONTENT_TYPE $content_type;
    uwsgi_param CONTENT_LENGTH $content_length;
    uwsgi_param REQUEST_URI $request_uri;
    uwsgi_param PATH_INFO $document_uri;
    uwsgi_param DOCUMENT_ROOT $document_root;
    uwsgi_param SERVER_PROTOCOL $server_protocol;
    uwsgi_param X_FORWARDED_FOR $proxy_add_x_forwarded_for;
    uwsgi_param REMOTE_ADDR $remote_addr;
    uwsgi_param REMOTE_PORT $remote_port;
    uwsgi_param SERVER_ADDR $server_addr;
    uwsgi_param SERVER_PORT $server_port;
    uwsgi_param SERVER_NAME $server_name;
"""
