# 050-clojure

## Purpose

Tests Hop3's **Clojure/JVM deployment** with Leiningen.

## What It Validates

- Clojure toolchain detection via `project.clj`
- Leiningen build process (`lein uberjar`)
- JVM application execution
- Pre-built JAR deployment

## Structure

```
Procfile       # web: java -jar target/uberjar/...standalone.jar
project.clj    # Leiningen project definition
src/           # Clojure source files
```

## Technical Details

- **Toolchain**: Clojure (detected via project.clj)
- **Build**: Leiningen uberjar (creates standalone JAR)
- **Runtime**: JVM
- **Procfile syntax**: `web: java -jar <path-to-jar>`

## Local Testing

```bash
lein uberjar
java -jar target/uberjar/sample-clojure-app-0.1.0-SNAPSHOT-standalone.jar
```

## Why This Test Matters

Clojure represents JVM-based deployments. This tests that Hop3 can handle the Leiningen build process and execute JVM applications, which also validates Java runtime availability.

## License

Copyright (c) 2019 John Simiyu. EPL-2.0.
