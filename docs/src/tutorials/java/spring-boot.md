# Deploying Spring Boot on Hop3

This guide walks you through deploying a Spring Boot application on Hop3. By the end, you'll have a production-ready Java application running on your own infrastructure.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/server-setup.md) if you haven't set one up yet
2. **The Hop3 CLI** - Installed on your local machine
3. **Java 17+** - Install from [Adoptium](https://adoptium.net/) or your package manager
4. **Maven 3.8+** - Install from [maven.apache.org](https://maven.apache.org/)
5. **Git** - For version control and deployment

Verify your local setup:

```bash
java -version 2>&1 | head -1
```

```bash
mvn -version | head -1
```

## Step 1: Create a New Spring Boot Application

Create the project directory:

```bash
mkdir hop3-tuto-spring-boot
```

Create the Maven build file:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>hop3-tuto-spring-boot</artifactId>
    <version>1.0.0</version>
    <name>hop3-tuto-spring-boot</name>
    <description>Spring Boot application for Hop3</description>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Create the source directory structure:

```bash
mkdir -p src/main/java/com/example/demo src/main/resources
```

## Step 2: Create the Application

Create the main application class:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MyappApplication {
    public static void main(String[] args) {
        SpringApplication.run(MyappApplication.class, args);
    }
}
```

Create a welcome controller:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.ResponseEntity;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;

@RestController
public class WelcomeController {

    @GetMapping("/")
    public ResponseEntity<String> index() {
        String html = """
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
                        background: linear-gradient(135deg, #6DB33F 0%, #34302D 100%);
                        color: white;
                    }
                    .container {
                        text-align: center;
                        padding: 2rem;
                    }
                    h1 { font-size: 3rem; margin-bottom: 1rem; }
                    p { font-size: 1.25rem; opacity: 0.9; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Hello from Hop3!</h1>
                    <p>Your Spring Boot application is running.</p>
                    <p>Current time: %s</p>
                </div>
            </body>
            </html>
            """.formatted(LocalDateTime.now());
        return ResponseEntity.ok()
            .header("Content-Type", "text/html")
            .body(html);
    }

    @GetMapping("/up")
    public String up() {
        return "OK";
    }

    @GetMapping("/api/info")
    public Map<String, Object> info() {
        Map<String, Object> info = new HashMap<>();
        info.put("name", "hop3-tuto-spring-boot");
        info.put("version", "1.0.0");
        info.put("javaVersion", System.getProperty("java.version"));
        info.put("springBootVersion", "3.2.0");
        return info;
    }
}
```

Create a health controller:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.lang.management.ManagementFactory;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;

@RestController
public class HealthController {

    @GetMapping("/health")
    public Map<String, Object> health() {
        Map<String, Object> health = new HashMap<>();
        health.put("status", "ok");
        health.put("timestamp", LocalDateTime.now().toString());

        // Memory info
        Runtime runtime = Runtime.getRuntime();
        Map<String, Object> memory = new HashMap<>();
        memory.put("max", runtime.maxMemory() / 1024 / 1024 + "MB");
        memory.put("total", runtime.totalMemory() / 1024 / 1024 + "MB");
        memory.put("free", runtime.freeMemory() / 1024 / 1024 + "MB");
        memory.put("used", (runtime.totalMemory() - runtime.freeMemory()) / 1024 / 1024 + "MB");
        health.put("memory", memory);

        // Uptime
        long uptime = ManagementFactory.getRuntimeMXBean().getUptime();
        health.put("uptime", uptime / 1000 + "s");

        return health;
    }
}
```

## Step 3: Configure the Application

Create the application configuration:

```text
# Server configuration
server.port=${PORT:8080}

# Application info
spring.application.name=hop3-tuto-spring-boot
info.app.name=hop3-tuto-spring-boot
info.app.version=1.0.0

# Actuator endpoints
management.endpoints.web.exposure.include=health,info,metrics
management.endpoint.health.show-details=always

# Logging
logging.level.root=INFO
logging.level.com.example=DEBUG
```

Create a production configuration:

```text
# Production-specific configuration
logging.level.root=WARN
logging.level.com.example=INFO

# Disable detailed error messages in production
server.error.include-message=never
server.error.include-stacktrace=never
```

## Step 4: Build and Verify

Build the application:

```bash
mvn clean package -DskipTests
```

```console
BUILD SUCCESS
```

Verify the JAR was created:

```bash
ls -la target/*.jar
```

Test the application starts correctly:

```bash
java -jar target/hop3-tuto-spring-boot-1.0.0.jar &
APP_PID=$!
sleep 10
curl -s http://localhost:8080/health | head -1 || echo "Server test completed"
kill $APP_PID 2>/dev/null || true
```

```console
status
```

## Step 5: Create Deployment Configuration

### Create a Procfile

Create a `Procfile` in your project root:

```procfile
# Pre-build: Build the JAR
prebuild: mvn clean package -DskipTests -Dspring.profiles.active=production

# Main web process
web: java -Dserver.port=$PORT -Dspring.profiles.active=production -jar target/hop3-tuto-spring-boot-1.0.0.jar
```

### Create hop3.toml

Create a `hop3.toml` for advanced configuration:

```toml
[metadata]
id = "hop3-tuto-spring-boot"
version = "1.0.0"
title = "My Spring Boot Application"

[build]
before-build = ["mvn clean package -DskipTests"]
packages = ["openjdk-17-jdk", "maven"]

[run]
start = "java -Dserver.port=$PORT -Dspring.profiles.active=production -jar target/hop3-tuto-spring-boot-1.0.0.jar"

[env]
JAVA_OPTS = "-Xmx512m -Xms256m"
SPRING_PROFILES_ACTIVE = "production"

[port]
web = 8080

[healthcheck]
path = "/actuator/health"
timeout = 60
interval = 60
```

Verify the deployment files exist:

```bash
ls -la Procfile hop3.toml
```

```console
Procfile
```

```console
hop3.toml
```

## Step 6: Initialize Git Repository

Create a `.gitignore` file:

```text
# Compiled class files
*.class

# Maven
target/
pom.xml.tag
pom.xml.releaseBackup
pom.xml.versionsBackup
pom.xml.next
release.properties

# Gradle
.gradle/
build/

# IDE
.idea/
*.iml
*.ipr
*.iws
.project
.classpath
.settings/
.vscode/

# OS files
.DS_Store
Thumbs.db

# Logs
*.log
logs/

# Environment
.env
application-local.properties
```

Initialize the repository:

```bash
git init
```

```console
Initialized empty Git repository
```

```bash
git add .
```

```bash
git commit -m "Initial Spring Boot application"
```

```console
Initial Spring Boot application
```

## Step 7: Deploy to Hop3

The following steps require a Hop3 server. Set the `HOP3_SERVER` environment variable to your server address before running these commands.

### Configure the CLI

If this is your first deployment, initialize Hop3:

```bash
hop3 init --ssh root@your-server.example.com
```

### Set Environment Variables

```bash
# Set JVM options
hop3 config set --app hop3-tuto-spring-boot JAVA_OPTS="-Xmx512m -Xms256m"

# Set Spring profile
hop3 config set --app hop3-tuto-spring-boot SPRING_PROFILES_ACTIVE=production
```

### Deploy

Deploy the application (first deployment creates the app):

```bash
hop3 deploy --app hop3-tuto-spring-boot
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 config set --app hop3-tuto-spring-boot HOST_NAME=hop3-tuto-spring-boot.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash
hop3 deploy --app hop3-tuto-spring-boot
```

Wait for the application to start:

```bash
sleep 5
```

You'll see output showing:
- Code upload
- Maven build (`mvn package`)
- Application startup

## Step 8: Verify Deployment

Check your application status:

```bash
hop3 app status --app hop3-tuto-spring-boot
```

```console
hop3-tuto-spring-boot
```

```bash
curl -s http://hop3-tuto-spring-boot.$HOP3_TEST_DOMAIN/up
```

```console
OK
```

View logs:

```bash
hop3 app logs --app hop3-tuto-spring-boot
```

Open your application:

```bash
# Your app will be available at:
# http://hop3-tuto-spring-boot.your-hop3-server.example.com

# Actuator endpoints at:
# http://hop3-tuto-spring-boot.your-hop3-server.example.com/actuator/health
# http://hop3-tuto-spring-boot.your-hop3-server.example.com/actuator/info
```

## Managing Your Application

### Restart the Application

```bash
hop3 app restart --app hop3-tuto-spring-boot
```

### View and Manage Environment Variables

```bash
# List all variables
hop3 config show --app hop3-tuto-spring-boot

# Set a variable
hop3 config set --app hop3-tuto-spring-boot NEW_VARIABLE=value

# Remove a variable
hop3 config unset --app hop3-tuto-spring-boot OLD_VARIABLE
```

### Scaling

```bash
# Check current processes
hop3 ps --app hop3-tuto-spring-boot

# Scale web workers
hop3 ps scale --app hop3-tuto-spring-boot web=2
```

## Advanced Configuration

### Adding a Database (PostgreSQL)

Add the PostgreSQL dependency to `pom.xml`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
```

Configure the database in `application-production.properties`:

```properties
spring.datasource.url=${DATABASE_URL}
spring.jpa.hibernate.ddl-auto=update
spring.jpa.properties.hibernate.dialect=org.hibernate.dialect.PostgreSQLDialect
```

Create and attach database:

```bash
hop3 addons create postgres hop3-tuto-spring-boot-db
hop3 addons attach hop3-tuto-spring-boot hop3-tuto-spring-boot-db
```

### Entity and Repository Example

```java
// src/main/java/com/example/demo/User.java
package com.example.demo;

import jakarta.persistence.*;

@Entity
@Table(name = "users")
public class User {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(unique = true, nullable = false)
    private String email;

    // Getters and setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
```

```java
// src/main/java/com/example/demo/UserRepository.java
package com.example.demo;

import org.springframework.data.jpa.repository.JpaRepository;

public interface UserRepository extends JpaRepository<User, Long> {
}
```

### Adding Redis for Caching

Add Redis dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

Configure Redis:

```properties
spring.data.redis.url=${REDIS_URL:redis://localhost:6379}
spring.cache.type=redis
```

Enable caching:

```java
@SpringBootApplication
@EnableCaching
public class MyappApplication {
    // ...
}
```

Attach Redis:

```bash
hop3 addons create redis hop3-tuto-spring-boot-redis
hop3 addons attach hop3-tuto-spring-boot hop3-tuto-spring-boot-redis
```

### Scheduled Tasks

Add scheduling support:

```java
@SpringBootApplication
@EnableScheduling
public class MyappApplication {
    // ...
}

@Component
public class ScheduledTasks {
    private static final Logger log = LoggerFactory.getLogger(ScheduledTasks.class);

    @Scheduled(fixedRate = 60000)
    public void reportCurrentTime() {
        log.info("Current time: {}", LocalDateTime.now());
    }

    @Scheduled(cron = "0 0 * * * *")
    public void hourlyTask() {
        log.info("Hourly task executed");
    }
}
```

### JVM Memory Tuning

Set JVM options for production:

```bash
hop3 config set --app hop3-tuto-spring-boot JAVA_OPTS="-Xmx512m -Xms256m -XX:+UseG1GC -XX:MaxGCPauseMillis=200"
```

Update `Procfile`:

```procfile
web: java $JAVA_OPTS -Dserver.port=$PORT -jar target/hop3-tuto-spring-boot-1.0.0.jar
```

### Building with Gradle

If you prefer Gradle, create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.2.0'
    id 'io.spring.dependency-management' version '1.1.4'
}

group = 'com.example'
version = '1.0.0'

java {
    sourceCompatibility = '17'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Update `Procfile`:

```procfile
prebuild: ./gradlew bootJar
web: java -Dserver.port=$PORT -jar build/libs/hop3-tuto-spring-boot-1.0.0.jar
```

### Native Image with GraalVM

For faster startup, compile to native image:

Add the GraalVM plugin:

```xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
</plugin>
```

Build native:

```bash
mvn -Pnative native:compile
```

Update `Procfile`:

```procfile
prebuild: mvn -Pnative native:compile
web: ./target/hop3-tuto-spring-boot
```

## Troubleshooting

### Application Won't Start

Check the logs for errors:

```bash
hop3 app logs --app hop3-tuto-spring-boot --tail
```

Common issues:
- **Port binding**: Ensure using `${PORT}` or `-Dserver.port=$PORT`
- **Memory issues**: Increase heap with `JAVA_OPTS`
- **Missing dependencies**: Check `mvn dependency:tree`

### Out of Memory Errors

Java applications can be memory-hungry. Tune the JVM:

```bash
# Limit heap size
hop3 config set --app hop3-tuto-spring-boot JAVA_OPTS="-Xmx256m -Xms128m"

# Use G1GC for better memory management
hop3 config set --app hop3-tuto-spring-boot JAVA_OPTS="-Xmx256m -XX:+UseG1GC"
```

### Slow Startup

Spring Boot can have slow startup times:

1. Use Spring Boot 3.2+ with AOT compilation
2. Exclude unused auto-configurations
3. Consider GraalVM native image
4. Use lazy initialization:

```properties
spring.main.lazy-initialization=true
```

### Database Connection Issues

Verify the database URL format for PostgreSQL:

```properties
# Spring Boot expects this format:
spring.datasource.url=jdbc:postgresql://host:port/database
spring.datasource.username=user
spring.datasource.password=pass

# Or use DATABASE_URL directly (Hop3 provides this):
spring.datasource.url=${DATABASE_URL}
```

### Build Failures

If Maven build fails:

```bash
# Check Maven version
mvn -version

# Clean and rebuild
mvn clean package -X  # verbose output
```

## Next Steps

- **[CLI Reference](../../reference/cli.md)** - Complete command reference
- **[hop3.toml Reference](../../reference/config.md)** - Full configuration options
- **[Backup and Restore Guide](../../guides/backup-restore.md)** - Protect your data

## Example Files

### Complete hop3.toml for Spring Boot

```toml
# hop3.toml - Spring Boot Application

[metadata]
id = "hop3-tuto-spring-boot"
version = "1.0.0"
title = "My Spring Boot Application"
author = "Your Name <you@example.com>"

[build]
before-build = ["mvn clean package -DskipTests"]
packages = ["openjdk-17-jdk", "maven"]

[run]
start = "java $JAVA_OPTS -Dserver.port=$PORT -Dspring.profiles.active=production -jar target/hop3-tuto-spring-boot-1.0.0.jar"
before-run = "java -jar target/hop3-tuto-spring-boot-1.0.0.jar --spring.flyway.enabled=true migrate"

[env]
JAVA_OPTS = "-Xmx512m -Xms256m -XX:+UseG1GC"
SPRING_PROFILES_ACTIVE = "production"

[port]
web = 8080

[healthcheck]
path = "/actuator/health"
timeout = 60
interval = 60

[[provider]]
name = "postgres"
plan = "standard"

[[provider]]
name = "redis"
plan = "basic"
```

### Complete Procfile for Spring Boot

```procfile
# Procfile - Spring Boot Application

# Build phase
prebuild: mvn clean package -DskipTests

# Pre-run hooks (database migrations with Flyway)
prerun: java -jar target/hop3-tuto-spring-boot-1.0.0.jar --spring.flyway.enabled=true migrate || true

# Web server
web: java $JAVA_OPTS -Dserver.port=$PORT -Dspring.profiles.active=production -jar target/hop3-tuto-spring-boot-1.0.0.jar

# Background worker (optional - using Spring Batch)
worker: java $JAVA_OPTS -Dspring.profiles.active=production -jar target/hop3-tuto-spring-boot-1.0.0.jar --spring.batch.job.enabled=true
```
