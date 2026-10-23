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
  server_name $HOST_NAME;

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

  # Largest request body this app accepts ([proxy] max-body-size). An app
  # that receives uploads raises it; nothing else on the box can.
  client_max_body_size $HOP3_INTERNAL_NGINX_MAX_BODY_SIZE;
  $HOP3_INTERNAL_NGINX_REQUEST_BUFFERING

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

  $HOP3_INTERNAL_NGINX_GATE
  $HOP3_INTERNAL_NGINX_CUSTOM_CLAUSES
  $HOP3_INTERNAL_NGINX_STATIC_MAPPINGS
  $HOP3_INTERNAL_NGINX_CACHE_MAPPINGS
  $HOP3_INTERNAL_NGINX_DENY
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
    $HOP3_INTERNAL_NGINX_GATE_HEADERS
    $NGINX_ACL
  }
"""

#: A php-fpm pool speaks FastCGI, so nginx is the thing that turns HTTP into
#: a PHP request: it resolves the file, passes the script name, and serves
#: everything that is not PHP itself. `try_files` sends unknown paths to the
#: front controller, which is what every PHP framework expects and what the
#: built-in server did implicitly.
NGINX_FASTCGI_FRAGMENT = """
  root $PHP_DOCUMENT_ROOT;
  index index.php;

  # A hidden file in the tree is configuration (.env, .htaccess, .git), and
  # the upstream .htaccess rules that would refuse it are Apache's, which
  # nginx never reads. First among the regex locations, so a script under a
  # hidden directory is refused rather than run. /.well-known stays open:
  # an app's CalDAV or WebFinger discovery lives there.
  location ~ /\\.(?!well-known/) { return 404; }

  location / {
    try_files $uri $uri/ /index.php?$query_string;
    $NGINX_ACL
  }

  location ~ [^/]\\.php(/|$) {
    fastcgi_split_path_info ^(.+?\\.php)(/.*)$;
    # Refuse a request whose script does not exist rather than handing the
    # path to index.php, which is the classic arbitrary-code-execution shape
    # for a misconfigured pool.
    if (!-f $document_root$fastcgi_script_name) { return 404; }
    fastcgi_pass $HOP3_INTERNAL_NGINX_FASTCGI_BACKEND;
    fastcgi_index index.php;
    include fastcgi_params;
    fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
    fastcgi_param PATH_INFO $fastcgi_path_info;
    fastcgi_param HTTPS $https if_not_empty;
    fastcgi_read_timeout 300;
    $HOP3_INTERNAL_NGINX_GATE_PARAMS
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

# `$uri/` sends a directory asked for without its slash to the slashed URL
# (301), so the relative links of its index.html resolve inside it; serving
# `$uri/index.html` in place resolved them against the parent. The redirect is
# relative: an absolute one names the port nginx listens on, which a client
# behind a port mapping cannot reach.
HOP3_INTERNAL_NGINX_STATIC_MAPPING = """
  location $static_url {
      sendfile on;
      sendfile_max_chunk 1m;
      tcp_nopush on;
      directio 8m;
      aio threads;
      root $static_path;
      absolute_redirect off;
      try_files $uri $uri/ $uri.html =404;
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
        $HOP3_INTERNAL_NGINX_GATE_HEADERS
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

#: The access gate (ADR 062), for the whole HTTPS server: nginx asks
#: hop3-server about every request before serving it. The check answers 2xx,
#: 401 (nginx sends the browser to sign in) or 403, with who is asking and the
#: request's cookies minus the gate's own. `/_hop3/auth/` is hop3-server's, on
#: the app's host, so the sign-in can set the gate cookie there.
NGINX_GATE_FRAGMENT = """
  auth_request /_hop3/gate-check;
  auth_request_set $hop3_user $upstream_http_x_hop3_user;
  auth_request_set $hop3_role $upstream_http_x_hop3_role;
  auth_request_set $hop3_cookie $upstream_http_cookie;
  auth_request_set $hop3_login $upstream_http_x_hop3_login;
  auth_request_set $hop3_state $upstream_http_x_hop3_state;
  error_page 401 = @hop3_sign_in;
  # auth_request discards the check's answer; fetch its 403 page again, which
  # names the role the account lacks. Only nginx's own 403s come here: an
  # app's 403 passes through untouched.
  error_page 403 @hop3_forbidden;

  location = /_hop3/gate-check {
    internal;
    auth_request off;
    proxy_pass http://$HOP3_INTERNAL_GATE_UPSTREAM/auth/check;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header X-Hop3-App $APP;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Uri $request_uri;
    proxy_set_header X-Forwarded-Proto $scheme;
  }

  location ^~ /_hop3/auth/ {
    auth_request off;
    proxy_pass http://$HOP3_INTERNAL_GATE_UPSTREAM;
    proxy_set_header Host $host;
    proxy_set_header X-Hop3-App $APP;
    proxy_set_header X-Forwarded-Proto $scheme;
  }

  location @hop3_sign_in {
    auth_request off;
    # The state cookie binding this sign-in to this browser (login CSRF).
    add_header Set-Cookie $hop3_state always;
    return 302 $hop3_login;
  }

  location @hop3_forbidden {
    auth_request off;
    rewrite ^ /auth/check? break;
    proxy_pass http://$HOP3_INTERNAL_GATE_UPSTREAM;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header X-Hop3-App $APP;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Uri $request_uri;
  }
"""

#: What a proxied request carries past the gate: the check's answers, never
#: the client's. An empty value drops the header.
NGINX_GATE_HEADERS = """
    proxy_set_header X-Hop3-User $hop3_user;
    proxy_set_header X-Hop3-Role $hop3_role;
    proxy_set_header Cookie $hop3_cookie;
"""

#: The same for a php-fpm pool: a parameter set here replaces the header nginx
#: would otherwise pass from the request.
NGINX_GATE_PARAMS = """
    fastcgi_param HTTP_X_HOP3_USER $hop3_user;
    fastcgi_param HTTP_X_HOP3_ROLE $hop3_role;
    fastcgi_param HTTP_COOKIE $hop3_cookie;
"""
