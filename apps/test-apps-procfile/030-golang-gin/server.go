package main

import (
	"github.com/gin-gonic/gin"
	"os"
)

var Router *gin.Engine

func homePage(c *gin.Context) {
	c.String(200, "Hello world!")
}

func main() {
	r := gin.Default()
	r.GET("/", homePage)

	var port = os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	r.Run(":" + port)
}
