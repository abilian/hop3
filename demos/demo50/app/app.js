// Copyright (c) 2025, Abilian SAS
// SPDX-License-Identifier: Apache-2.0
//
// Demo 50: Native Node.js/Express application
// Same app as demo18, but deployed natively without Docker

const express = require('express');

const app = express();
const port = process.env.PORT || 3000;
const addr = process.env.BIND_ADDRESS || '127.0.0.1';

// Store some state in memory
let requestCount = 0;
const startTime = new Date();

app.use(express.json());

// Home endpoint
app.get('/', (req, res) => {
    res.json({
        app: 'demo50',
        type: 'native-nodejs',
        message: 'Welcome to demo50 - Native Node.js/Express!',
        runtime: `Node.js ${process.version}`,
    });
});

// Info endpoint
app.get('/info', (req, res) => {
    res.json({
        node_version: process.version,
        platform: process.platform,
        arch: process.arch,
        uptime_seconds: process.uptime(),
        memory: process.memoryUsage(),
        env: {
            NODE_ENV: process.env.NODE_ENV || 'development',
            PORT: port,
        },
    });
});

// Stats endpoint
app.get('/stats', (req, res) => {
    requestCount++;
    const uptime = Math.floor((new Date() - startTime) / 1000);
    res.json({
        requests: requestCount,
        uptime_seconds: uptime,
        started_at: startTime.toISOString(),
    });
});

// Echo endpoint (POST)
app.post('/echo', (req, res) => {
    res.json({
        received: req.body,
        headers: {
            'content-type': req.headers['content-type'],
            'user-agent': req.headers['user-agent'],
        },
    });
});

// Calculate endpoint
app.get('/calculate/:operation/:a/:b', (req, res) => {
    const { operation, a, b } = req.params;
    const numA = parseFloat(a);
    const numB = parseFloat(b);

    if (isNaN(numA) || isNaN(numB)) {
        return res.status(400).json({ error: 'Invalid numbers' });
    }

    let result;
    switch (operation) {
        case 'add':
            result = numA + numB;
            break;
        case 'subtract':
            result = numA - numB;
            break;
        case 'multiply':
            result = numA * numB;
            break;
        case 'divide':
            if (numB === 0) {
                return res.status(400).json({ error: 'Division by zero' });
            }
            result = numA / numB;
            break;
        default:
            return res.status(400).json({ error: 'Unknown operation' });
    }

    res.json({
        operation,
        a: numA,
        b: numB,
        result,
    });
});

// Health check
app.get('/health', (req, res) => {
    res.json({ status: 'healthy' });
});

// Start server
app.listen(port, addr, () => {
    console.log(`Demo50 native app listening on ${addr}:${port}`);
});
