<?php
// Copyright (c) 2025, Abilian SAS
// SPDX-License-Identifier: Apache-2.0
//
// Demo 53: PHP JSON API application
// Feature-rich API similar to demo50-52

// Enable error reporting for development
error_reporting(E_ALL);
ini_set('display_errors', '0');

// File-based counter for stats (works with Apache mod_php)
$counter_file = '/tmp/demo53_counter.json';
function get_counter_data() {
    global $counter_file;
    if (file_exists($counter_file)) {
        $data = json_decode(file_get_contents($counter_file), true);
        if ($data) return $data;
    }
    return ['start_time' => time(), 'request_count' => 0];
}

function save_counter_data($data) {
    global $counter_file;
    file_put_contents($counter_file, json_encode($data), LOCK_EX);
}

// Set JSON content type
header('Content-Type: application/json');

// Get request path
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$method = $_SERVER['REQUEST_METHOD'];

// Router
try {
    switch (true) {
        case $path === '/' && $method === 'GET':
            echo json_encode([
                'app' => 'demo53',
                'type' => 'docker-php',
                'message' => 'Welcome to demo53 - PHP JSON API!',
                'runtime' => 'PHP ' . PHP_VERSION
            ]);
            break;

        case $path === '/info' && $method === 'GET':
            echo json_encode([
                'php_version' => PHP_VERSION,
                'php_sapi' => PHP_SAPI,
                'os' => PHP_OS,
                'arch' => php_uname('m'),
                'env' => [
                    'PORT' => getenv('PORT') ?: 'not set'
                ]
            ]);
            break;

        case $path === '/stats' && $method === 'GET':
            $data = get_counter_data();
            $data['request_count']++;
            save_counter_data($data);
            $uptime = time() - $data['start_time'];
            echo json_encode([
                'requests' => $data['request_count'],
                'uptime_seconds' => $uptime,
                'started_at' => date('c', $data['start_time'])
            ]);
            break;

        case $path === '/echo' && $method === 'POST':
            $body = file_get_contents('php://input');
            $received = json_decode($body, true);
            if ($received === null && json_last_error() !== JSON_ERROR_NONE) {
                $received = $body;
            }
            echo json_encode([
                'received' => $received,
                'headers' => [
                    'content-type' => $_SERVER['CONTENT_TYPE'] ?? null,
                    'user-agent' => $_SERVER['HTTP_USER_AGENT'] ?? null
                ]
            ]);
            break;

        case preg_match('#^/calculate/(\w+)/([0-9.]+)/([0-9.]+)$#', $path, $matches) && $method === 'GET':
            $operation = $matches[1];
            $a = (float)$matches[2];
            $b = (float)$matches[3];

            switch ($operation) {
                case 'add':
                    $result = $a + $b;
                    break;
                case 'subtract':
                    $result = $a - $b;
                    break;
                case 'multiply':
                    $result = $a * $b;
                    break;
                case 'divide':
                    if ($b == 0) {
                        http_response_code(400);
                        echo json_encode(['error' => 'Division by zero']);
                        exit;
                    }
                    $result = $a / $b;
                    break;
                default:
                    http_response_code(400);
                    echo json_encode(['error' => 'Unknown operation']);
                    exit;
            }

            echo json_encode([
                'operation' => $operation,
                'a' => $a,
                'b' => $b,
                'result' => $result
            ]);
            break;

        case preg_match('#^/fib/(\d+)$#', $path, $matches) && $method === 'GET':
            $n = (int)$matches[1];

            if ($n < 0 || $n > 40) {
                http_response_code(400);
                echo json_encode(['error' => 'n must be between 0 and 40']);
                exit;
            }

            $start = microtime(true);
            $result = fibonacci($n);
            $duration = (int)((microtime(true) - $start) * 1000);

            echo json_encode([
                'n' => $n,
                'result' => $result,
                'duration_ms' => $duration
            ]);
            break;

        case $path === '/health' && $method === 'GET':
            echo json_encode(['status' => 'healthy']);
            break;

        default:
            http_response_code(404);
            echo json_encode(['error' => 'Not found']);
            break;
    }
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['error' => $e->getMessage()]);
}

// Helper function
function fibonacci($n) {
    if ($n <= 1) {
        return $n;
    }
    return fibonacci($n - 1) + fibonacci($n - 2);
}
