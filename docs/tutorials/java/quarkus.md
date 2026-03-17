---
tutorial:
  name: quarkus-hop3-tutorial
  teardown:
  - rm -rf hop3-tuto-quarkus 2>/dev/null || true
  - hop3 app:destroy hop3-tuto-quarkus -y 2>/dev/null || true
---

# Deploying Quarkus on Hop3

This guide walks you through deploying a Quarkus application on Hop3. Quarkus is a Kubernetes-native Java framework optimized for fast startup and low memory usage.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/installation.md)
2. **The Hop3 CLI** - Installed on your local machine
3. **Java 17+** - Install from [Adoptium](https://adoptium.net/)
4. **Maven 3.8+** - Install from [maven.apache.org](https://maven.apache.org/)
5. **Git** - For version control and deployment

Verify your local setup:

```bash exec id=check-java
java -version 2>&1 | head -1
```

```output regex
(openjdk|java) version "[0-9]+
```

```bash exec id=check-mvn
mvn -version | head -1
```

```output regex
Apache Maven [0-9]+\.
```

## Step 1: Create a New Quarkus Application

Create project using Maven:

```bash exec id=create-project timeout=180
mvn io.quarkus.platform:quarkus-maven-plugin:3.6.0:create \
    -DprojectGroupId=com.example \
    -DprojectArtifactId=hop3-tuto-quarkus \
    -Dextensions="resteasy-reactive-jackson,smallrye-health" \
    -DnoCode
```

```output contains
BUILD SUCCESS
```

```assert file-exists path=hop3-tuto-quarkus/pom.xml
```

## Step 2: Create the Application

Create the resource directory:

```bash exec id=create-dirs dir=hop3-tuto-quarkus
mkdir -p src/main/java/com/example src/main/resources/META-INF/resources
```

Create the main resource:

```file path=hop3-tuto-quarkus/src/main/java/com/example/WelcomeResource.java
package com.example;

import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import java.time.Instant;

@Path("/")
public class WelcomeResource {

    @GET
    @Produces(MediaType.TEXT_HTML)
    public String index() {
        return """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Welcome to Hop3</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #4695EB 0%, #1a237e 100%);
                        color: white;
                    }
                    .container { text-align: center; padding: 2rem; }
                    h1 { font-size: 3rem; margin-bottom: 1rem; }
                    p { font-size: 1.25rem; opacity: 0.9; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Hello from Hop3!</h1>
                    <p>Your Quarkus application is running.</p>
                    <p>Current time: %s</p>
                </div>
            </body>
            </html>
            """.formatted(Instant.now());
    }

    @GET
    @Path("/up")
    @Produces(MediaType.TEXT_PLAIN)
    public String up() {
        return "OK";
    }
}
```

Create an API resource:

```file path=hop3-tuto-quarkus/src/main/java/com/example/InfoResource.java
package com.example;

import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import java.util.Map;

@Path("/api")
public class InfoResource {

    @GET
    @Path("/info")
    @Produces(MediaType.APPLICATION_JSON)
    public Map<String, Object> info() {
        return Map.of(
            "name", "hop3-tuto-quarkus",
            "version", "1.0.0",
            "javaVersion", System.getProperty("java.version"),
            "quarkusVersion", io.quarkus.runtime.Quarkus.class.getPackage().getImplementationVersion()
        );
    }
}
```

Create application configuration:

```file path=hop3-tuto-quarkus/src/main/resources/application.properties
# HTTP configuration
quarkus.http.host=0.0.0.0
quarkus.http.port=${PORT:8080}

# Application info
quarkus.application.name=hop3-tuto-quarkus
quarkus.application.version=1.0.0

# Health checks
quarkus.smallrye-health.root-path=/q/health

# Logging
quarkus.log.level=INFO
quarkus.log.console.format=%d{HH:mm:ss} %-5p [%c{2.}] %s%e%n
```

## Step 3: Build and Test

Build the application:

```bash exec id=build-app dir=hop3-tuto-quarkus timeout=300
./mvnw package -DskipTests
```

```output contains
BUILD SUCCESS
```

Verify the JAR:

```bash exec id=verify-jar dir=hop3-tuto-quarkus
ls -la target/quarkus-app/
```

```output contains
quarkus-run.jar
```

Test the application:

```bash exec id=test-app dir=hop3-tuto-quarkus timeout=30
java -jar target/quarkus-app/quarkus-run.jar &
APP_PID=$!
sleep 5
curl -s http://localhost:8080/up || echo "Test completed"
kill $APP_PID 2>/dev/null || true
```

```output contains
OK
```

## Step 4: Create Deployment Configuration

```file path=hop3-tuto-quarkus/Procfile
prebuild: ./mvnw package -DskipTests
web: java -jar target/quarkus-app/quarkus-run.jar
```

```file path=hop3-tuto-quarkus/hop3.toml
[metadata]
id = "hop3-tuto-quarkus"
version = "1.0.0"
title = "My Quarkus Application"

[build]
before-build = ["./mvnw package -DskipTests"]
packages = ["openjdk-17-jdk", "maven"]

[run]
start = "java -jar target/quarkus-app/quarkus-run.jar"

[env]
QUARKUS_PROFILE = "prod"

[port]
web = 8080

[healthcheck]
path = "/q/health/ready"
timeout = 30
interval = 60
```

## Deploy to Hop3

The following steps require a Hop3 server.

### Initialize (First Time Only)

```bash skip
hop3 init --ssh root@your-server.example.com
```

### Set Environment Variables

```bash skip
hop3 config:set hop3-tuto-quarkus QUARKUS_PROFILE=prod
```

### Deploy

Deploy the application (first deployment creates the app):

```bash exec id=deploy dir=hop3-tuto-quarkus timeout=120
hop3 deploy hop3-tuto-quarkus
```

```output contains
deployed successfully
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash exec id=set-hostname timeout=30
hop3 config:set hop3-tuto-quarkus HOST_NAME=hop3-tuto-quarkus.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash exec id=redeploy dir=hop3-tuto-quarkus timeout=120
hop3 deploy hop3-tuto-quarkus
```

```output contains
deployed successfully
```

### Verify Deployment

```bash exec id=check-status timeout=30
hop3 app:status hop3-tuto-quarkus
```

```output contains
hop3-tuto-quarkus
```

```bash exec id=check-health timeout=30
curl -s http://hop3-tuto-quarkus.$HOP3_TEST_DOMAIN/up
```

```output contains
OK
```

View logs:

```bash skip
# View logs
hop3 app:logs hop3-tuto-quarkus

# Your app will be available at:
# http://hop3-tuto-quarkus.your-hop3-server.example.com
```

### Managing Your Application

```bash skip
# Restart the application
hop3 app:restart hop3-tuto-quarkus

# View/set environment variables
hop3 config:show hop3-tuto-quarkus
hop3 config:set hop3-tuto-quarkus NEW_VAR=value

# Scale workers
hop3 ps:scale hop3-tuto-quarkus web=2
```

## Advanced Configuration

### Native Compilation with GraalVM

```bash skip
./mvnw package -Pnative
```

Update Procfile for native:

```procfile
prebuild: ./mvnw package -Pnative
web: ./target/hop3-tuto-quarkus-1.0.0-runner
```

### Database with Panache

Add extension:

```bash skip
./mvnw quarkus:add-extension -Dextensions="hibernate-orm-panache,jdbc-postgresql"
```

```java
@Entity
public class Item extends PanacheEntity {
    public String name;
    public Double price;
}
```

### Reactive with Mutiny

```java
@GET
@Path("/items")
public Uni<List<Item>> list() {
    return Item.listAll();
}
```

## Example hop3.toml

```toml
[metadata]
id = "hop3-tuto-quarkus"
version = "1.0.0"

[build]
before-build = ["./mvnw package -DskipTests"]

[run]
start = "java -Dquarkus.http.port=$PORT -jar target/quarkus-app/quarkus-run.jar"

[env]
QUARKUS_PROFILE = "prod"

[port]
web = 8080

[healthcheck]
path = "/q/health/ready"

[[provider]]
name = "postgres"
plan = "standard"
```
