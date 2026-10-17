# 156-flask-mysql

Smoke test for the Hop3 MySQL addon: declares `[[addons]] type = "mysql"`, then writes a row and reads it back through the injected credentials.

The sibling of `155-flask-redis`. Declaring the addon is also what makes the e2e target install MySQL, which no test layer had: the backup e2e uses this app to check that a dump holds the data, logs no access error, and restores.
