package main

import (
	"fmt"
	"net"
	"os"
	"time"
)

const defaultAddress = "127.0.0.1:8080"

func main() {
	address := os.Getenv("CODESTRA_HEALTHCHECK_ADDRESS")
	if address == "" {
		address = defaultAddress
	}

	connection, err := net.DialTimeout("tcp", address, 5*time.Second)
	if err != nil {
		fmt.Fprintf(os.Stderr, "listener check failed for %s: %v\n", address, err)
		os.Exit(1)
	}
	_ = connection.Close()
}
