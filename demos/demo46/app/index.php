<?php
// Demo 46: Minimal PHP + MySQL connectivity test

$host = getenv('MYSQL_HOST') ?: 'localhost';
$port = getenv('MYSQL_PORT') ?: '3306';
$database = getenv('MYSQL_DATABASE') ?: 'demo46';
$user = getenv('MYSQL_USER') ?: 'demo46';
$password = getenv('MYSQL_PASSWORD') ?: '';

?>
<!DOCTYPE html>
<html>
<head>
    <title>Demo 46: PHP + MySQL</title>
</head>
<body>
    <h1>Demo 46: PHP + MySQL</h1>
    <p>This is a minimal PHP app testing MySQL connectivity.</p>

    <h2>Database Connection Test</h2>
    <?php
    try {
        $mysqli = new mysqli($host, $user, $password, $database, (int)$port);

        if ($mysqli->connect_error) {
            echo "<p style='color: red;'>Connection failed: " . htmlspecialchars($mysqli->connect_error) . "</p>";
        } else {
            echo "<p style='color: green;'>Connected successfully!</p>";

            // Get MySQL version
            $result = $mysqli->query("SELECT VERSION() as version");
            if ($result) {
                $row = $result->fetch_assoc();
                echo "<p>MySQL Version: " . htmlspecialchars($row['version']) . "</p>";
            }

            $mysqli->close();
        }
    } catch (Exception $e) {
        echo "<p style='color: red;'>Error: " . htmlspecialchars($e->getMessage()) . "</p>";
    }
    ?>

    <h2>Environment</h2>
    <ul>
        <li>MYSQL_HOST: <?php echo htmlspecialchars($host); ?></li>
        <li>MYSQL_PORT: <?php echo htmlspecialchars($port); ?></li>
        <li>MYSQL_DATABASE: <?php echo htmlspecialchars($database); ?></li>
        <li>MYSQL_USER: <?php echo htmlspecialchars($user); ?></li>
    </ul>
</body>
</html>
