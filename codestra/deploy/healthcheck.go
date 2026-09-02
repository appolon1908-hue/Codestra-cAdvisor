package main

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"time"
)

const (
	defaultHealthURL = "http://127.0.0.1:8080/healthz"
	maximumBodyBytes = 1024
)

func validateHealthURL(raw string) (*url.URL, error) {
	parsed, err := url.Parse(raw)
	if err != nil {
		return nil, fmt.Errorf("parse health URL: %w", err)
	}
	if parsed.Scheme != "http" {
		return nil, fmt.Errorf("health URL must use internal HTTP")
	}
	if parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" || parsed.Path != "/healthz" {
		return nil, fmt.Errorf("health URL must be an exact /healthz request without credentials, query, or fragment")
	}
	switch parsed.Hostname() {
	case "127.0.0.1", "localhost", "cadvisor":
	default:
		return nil, fmt.Errorf("health URL host is outside the approved container boundary")
	}
	if parsed.Port() == "" {
		return nil, fmt.Errorf("health URL must use an explicit port")
	}
	return parsed, nil
}

func checkHealth(ctx context.Context, raw string) error {
	parsed, err := validateHealthURL(raw)
	if err != nil {
		return err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, parsed.String(), nil)
	if err != nil {
		return fmt.Errorf("create health request: %w", err)
	}
	request.Header.Set("Accept", "text/plain")
	client := &http.Client{
		Transport: &http.Transport{
			Proxy:                 nil,
			DisableCompression:    true,
			ResponseHeaderTimeout: 4 * time.Second,
		},
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
			return fmt.Errorf("health redirects are prohibited")
		},
	}
	response, err := client.Do(request)
	if err != nil {
		return fmt.Errorf("health request failed: %w", err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, maximumBodyBytes+1))
	if err != nil {
		return fmt.Errorf("read health response: %w", err)
	}
	if len(body) > maximumBodyBytes {
		return fmt.Errorf("health response exceeded %d bytes", maximumBodyBytes)
	}
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return fmt.Errorf("health endpoint returned HTTP %d", response.StatusCode)
	}
	return nil
}

func main() {
	healthURL := os.Getenv("CODESTRA_HEALTHCHECK_URL")
	if healthURL == "" {
		healthURL = defaultHealthURL
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := checkHealth(ctx, healthURL); err != nil {
		fmt.Fprintf(os.Stderr, "readiness check failed: %v\n", err)
		os.Exit(1)
	}
}
