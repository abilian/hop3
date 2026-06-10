# Deploying Java on Hop3

A Java app on Hop3 is a single self-contained JAR that Hop3 builds with Maven (or Gradle) on the server, then runs as one long-lived JVM process. The framework's embedded HTTP server (Tomcat for Spring Boot, Vert.x for Quarkus) binds to the port Hop3 hands it through `$PORT`, and nginx proxies your public hostname to that port. There is no separate application server to install and no servlet container to configure — you ship a JAR and a few lines of `hop3.toml`.

This page covers what every Java deployment has in common. Read it first, then follow the framework guide below that matches your stack.

## How Hop3 builds and runs Java

The flow is the same for every framework here:

1. **Toolchain** — Hop3 installs a JDK and Maven on the server via `[build].packages` (e.g. `openjdk-17-jdk`, `maven`). If your project ships the Maven wrapper (`./mvnw`), you can use it instead of a system Maven.
2. **Build** — `[build].before-build` runs the packaging command (`mvn clean package -DskipTests` or `./mvnw package -DskipTests`), producing a runnable JAR under `target/`.
3. **Run** — `[run].start` launches a single JVM: `java ... -jar target/<your-app>.jar`. The process stays up; Hop3 supervises it and restarts it if it dies.
4. **Proxy** — your app must listen on the dynamic `$PORT` Hop3 assigns, on all interfaces. nginx terminates the public hostname (set via `HOST_NAME`) and forwards to that port.

The one rule that matters: **bind to `$PORT`, not a hardcoded port.** The two frameworks expose this differently — Spring Boot via `-Dserver.port=$PORT` (or `server.port=${PORT:8080}` in `application.properties`), Quarkus via `-Dquarkus.http.port=$PORT` (or `quarkus.http.port=${PORT:8080}`). The `[port]` block in `hop3.toml` only records the container's default port; the live port comes from `$PORT` at runtime.

A representative `hop3.toml` for a Java app:

```toml
[metadata]
id = "my-java-app"
version = "1.0.0"

[build]
before-build = ["mvn clean package -DskipTests"]
packages = ["openjdk-17-jdk", "maven"]

[run]
start = "java $JAVA_OPTS -Dserver.port=$PORT -jar target/my-java-app-1.0.0.jar"

[env]
JAVA_OPTS = "-Xmx512m -Xms256m"

[port]
web = 8080

[healthcheck]
path = "/actuator/health"
```

## Notes that apply to every Java app

- **Memory is your main tuning knob.** The JVM is memory-hungry. Set heap limits through a `JAVA_OPTS` env var (e.g. `-Xmx512m -Xms256m -XX:+UseG1GC`) and reference it in your `start` command. Out-of-memory kills show up as the process restarting under load.
- **Builds are heavy; let Hop3 cache them.** Maven downloads its dependency tree on the first deploy. Keep `target/` out of git (`.gitignore`) and let the server build — don't commit JARs.
- **Addons are injected as env vars.** Attaching a database or cache exposes `DATABASE_URL` / `REDIS_URL` to the process. Wire them in via your framework's config — Spring Boot reads `spring.datasource.url=${DATABASE_URL}`, Quarkus reads the equivalent datasource properties. Create and attach with `hop3 addons create postgres <name>` then `hop3 addons attach <app> <name>`.
- **Health checks point at the framework's endpoint, not `/`.** Spring Boot Actuator serves `/actuator/health`; Quarkus SmallRye Health serves `/q/health/ready`. Set `[healthcheck].path` accordingly so Hop3 knows when the (slow-starting) JVM is actually ready.
- **Startup is slow on the JVM.** Cold start can take several seconds; give the health check enough `timeout`. For faster startup and a smaller footprint, both frameworks support GraalVM native images — you then run the native binary directly instead of `java -jar`.

## Choose a framework

| Framework | Tutorial | When to pick it |
|-----------|----------|-----------------|
| Spring Boot | [Spring Boot](spring-boot.md) | The mainstream choice — rich ecosystem, Actuator health endpoints, JPA/Redis starters, embedded Tomcat. |
| Quarkus | [Quarkus](quarkus.md) | Fast startup and low memory, reactive/Mutiny support, first-class GraalVM native images. |

Both build a JAR with Maven and run a JVM bound to `$PORT` — the config differs only in the framework's port/health properties and start command.
