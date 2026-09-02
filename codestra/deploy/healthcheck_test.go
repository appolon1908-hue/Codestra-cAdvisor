package main

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestValidateHealthURLBoundary(t *testing.T) {
	t.Parallel()
	valid := []string{
		"http://127.0.0.1:2375/healthz",
		"http://localhost:8080/healthz",
		"http://cadvisor:8080/healthz",
	}
	for _, candidate := range valid {
		if _, err := validateHealthURL(candidate); err != nil {
			t.Fatalf("expected %q to be valid: %v", candidate, err)
		}
	}
	invalid := []string{
		"https://127.0.0.1:9443/healthz",
		"http://example.com:8080/healthz",
		"http://127.0.0.1:8080/metrics",
		"http://127.0.0.1:8080/healthz?debug=1",
		"http://user:pass@127.0.0.1:8080/healthz",
		"http://127.0.0.1/healthz",
	}
	for _, candidate := range invalid {
		if _, err := validateHealthURL(candidate); err == nil {
			t.Fatalf("expected %q to be rejected", candidate)
		}
	}
}

func TestCheckHealthRequiresSuccessfulBoundedResponse(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name       string
		status     int
		body       string
		wantErr    bool
	}{
		{name: "ready", status: http.StatusOK, body: "ok\n"},
		{name: "unavailable", status: http.StatusServiceUnavailable, body: "unavailable\n", wantErr: true},
		{name: "oversized", status: http.StatusOK, body: strings.Repeat("x", maximumBodyBytes+1), wantErr: true},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Method != http.MethodGet || r.URL.Path != "/healthz" {
					t.Fatalf("unexpected request: %s %s", r.Method, r.URL.String())
				}
				w.WriteHeader(test.status)
				_, _ = fmt.Fprint(w, test.body)
			}))
			defer server.Close()
			ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
			defer cancel()
			err := checkHealth(ctx, server.URL+"/healthz")
			if test.wantErr && err == nil {
				t.Fatal("expected readiness failure")
			}
			if !test.wantErr && err != nil {
				t.Fatalf("unexpected readiness failure: %v", err)
			}
		})
	}
}

func TestCheckHealthRejectsRedirect(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "/healthz", http.StatusTemporaryRedirect)
	}))
	defer server.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if err := checkHealth(ctx, server.URL+"/healthz"); err == nil {
		t.Fatal("expected redirect to fail readiness")
	}
}
