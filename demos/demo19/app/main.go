// Copyright (c) 2025, Abilian SAS
// SPDX-License-Identifier: Apache-2.0
//
// Demo 19: Docker Go application using Gin framework

package main

import (
	"net/http"
	"os"
	"runtime"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
)

var (
	startTime    = time.Now()
	requestCount int64
)

func main() {
	// Set gin mode
	if os.Getenv("GIN_MODE") == "" {
		gin.SetMode(gin.ReleaseMode)
	}

	r := gin.Default()

	// Home endpoint
	r.GET("/", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"app":     "demo19",
			"type":    "docker-go",
			"message": "Welcome to demo19 - Docker Go/Gin!",
			"runtime": runtime.Version(),
		})
	})

	// Info endpoint
	r.GET("/info", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"go_version": runtime.Version(),
			"os":         runtime.GOOS,
			"arch":       runtime.GOARCH,
			"cpus":       runtime.NumCPU(),
			"goroutines": runtime.NumGoroutine(),
		})
	})

	// Stats endpoint
	r.GET("/stats", func(c *gin.Context) {
		requestCount++
		uptime := time.Since(startTime).Seconds()
		c.JSON(http.StatusOK, gin.H{
			"requests":       requestCount,
			"uptime_seconds": int64(uptime),
			"started_at":     startTime.Format(time.RFC3339),
		})
	})

	// Calculator endpoint
	r.GET("/calculate/:operation/:a/:b", func(c *gin.Context) {
		operation := c.Param("operation")
		a, errA := strconv.ParseFloat(c.Param("a"), 64)
		b, errB := strconv.ParseFloat(c.Param("b"), 64)

		if errA != nil || errB != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid numbers"})
			return
		}

		var result float64
		switch operation {
		case "add":
			result = a + b
		case "subtract":
			result = a - b
		case "multiply":
			result = a * b
		case "divide":
			if b == 0 {
				c.JSON(http.StatusBadRequest, gin.H{"error": "Division by zero"})
				return
			}
			result = a / b
		default:
			c.JSON(http.StatusBadRequest, gin.H{"error": "Unknown operation"})
			return
		}

		c.JSON(http.StatusOK, gin.H{
			"operation": operation,
			"a":         a,
			"b":         b,
			"result":    result,
		})
	})

	// Fibonacci endpoint (showcases Go performance)
	r.GET("/fib/:n", func(c *gin.Context) {
		n, err := strconv.Atoi(c.Param("n"))
		if err != nil || n < 0 || n > 40 {
			c.JSON(http.StatusBadRequest, gin.H{"error": "n must be between 0 and 40"})
			return
		}

		start := time.Now()
		result := fibonacci(n)
		duration := time.Since(start)

		c.JSON(http.StatusOK, gin.H{
			"n":           n,
			"result":      result,
			"duration_ms": duration.Milliseconds(),
		})
	})

	// Health check
	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "healthy"})
	})

	// Get port from environment
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	r.Run(":" + port)
}

func fibonacci(n int) int {
	if n <= 1 {
		return n
	}
	return fibonacci(n-1) + fibonacci(n-2)
}
