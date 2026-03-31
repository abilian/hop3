package main

import (
	"os"

	"github.com/gin-gonic/gin"
)

func homePage(c *gin.Context) {
	c.String(200, "Hello World, from Go/Gin via Nix!")
}

func main() {
	r := gin.Default()
	r.GET("/", homePage)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	bindAddr := os.Getenv("BIND_ADDRESS")
	if bindAddr == "" {
		bindAddr = "127.0.0.1"
	}

	r.Run(bindAddr + ":" + port)
}
