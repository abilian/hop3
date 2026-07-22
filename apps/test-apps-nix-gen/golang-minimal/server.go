package main

import (
	"fmt"
	"net/http"
	"os"
)

func handler(w http.ResponseWriter, r *http.Request) {
	fmt.Fprint(w, "Hello World, from Go (minimal) via Nix!")
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	bindAddr := os.Getenv("BIND_ADDRESS")
	if bindAddr == "" {
		bindAddr = "127.0.0.1"
	}

	addr := bindAddr + ":" + port
	http.HandleFunc("/", handler)
	fmt.Printf("Server listening on %s\n", addr)
	http.ListenAndServe(addr, nil)
}
