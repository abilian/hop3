# Failing Test Apps

Apps that currently fail deployment and need fixes. These are not intentionally broken - they represent gaps in Hop3's toolchain support or missing features.

## Status

| App | Stack | Status | Blocker |
|-----|-------|--------|---------|
| `030-rack` | Ruby | Toolchain gap | Rack/rackup not supported |
| `120-flask-pip-alt` | Python | Feature gap | Alternate config paths not supported |
| `clojure` | Clojure | Toolchain gap | No Clojure/Leiningen toolchain |

## Details

### 030-rack

Ruby Rack application using `bundle exec rackup --port $PORT`. The working Sinatra app (`test-apps/040-sinatra`) uses direct Ruby execution (`bundle exec ruby app.rb`).

**Blocker:** Hop3's Ruby toolchain doesn't support Rack's `rackup` command for process management.

**Fix options:**
1. Add rackup/Puma support to Ruby toolchain
2. Convert to use direct Ruby execution with Puma

### 120-flask-pip-alt

Flask app with Procfile in `hop3/` subdirectory instead of project root. Tests alternate configuration path feature.

**Blocker:** Hop3 only looks for Procfile/hop3.toml in project root.

**Fix:** Implement alternate config path detection (check `hop3/` subdirectory).

### clojure

Clojure web server using Leiningen (`lein run`).

**Blocker:** No Clojure toolchain in Hop3.

**Fix options:**
1. Add Clojure/Leiningen toolchain (detect `project.clj`)
2. Add JVM/uberjar support (pre-built JAR deployment)
3. Convert to use pre-built uberjar with Java toolchain
