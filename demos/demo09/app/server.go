package main

import (
	"io"
	"net/http"
	"os"
)

func getRoot(w http.ResponseWriter, r *http.Request) {
	io.WriteString(w, "Welcome to demo09\n")
}

func main() {
	http.HandleFunc("/", getRoot)

	http.ListenAndServe(":"+os.Getenv("PORT"), nil)
}
