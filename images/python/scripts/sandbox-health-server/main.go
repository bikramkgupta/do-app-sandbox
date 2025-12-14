package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"
)

// HealthResponse represents the JSON response for the health endpoint
type HealthResponse struct {
	Status    string `json:"status"`
	Service   string `json:"service"`
	Timestamp string `json:"timestamp"`
}

// healthHandler handles requests to the /sandbox_health endpoint
func healthHandler(w http.ResponseWriter, r *http.Request) {
	// Only respond to /sandbox_health endpoint
	if r.URL.Path != "/sandbox_health" {
		http.NotFound(w, r)
		return
	}

	// Create health response
	response := HealthResponse{
		Status:    "ok",
		Service:   "sandbox",
		Timestamp: time.Now().UTC().Format(time.RFC3339),
	}

	// Set content type header
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)

	// Encode and send JSON response
	if err := json.NewEncoder(w).Encode(response); err != nil {
		log.Printf("Error encoding JSON response: %v", err)
	}
}

func main() {
	// Get port from environment variable, default to 9090
	port := 9090
	if portStr := os.Getenv("SANDBOX_HEALTH_PORT"); portStr != "" {
		if p, err := strconv.Atoi(portStr); err == nil {
			port = p
		} else {
			log.Printf("Warning: Invalid SANDBOX_HEALTH_PORT value '%s', using default %d", portStr, port)
		}
	}

	// Create HTTP server
	mux := http.NewServeMux()
	mux.HandleFunc("/sandbox_health", healthHandler)

	server := &http.Server{
		Addr:         fmt.Sprintf("0.0.0.0:%d", port),
		Handler:      mux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	// Log server start
	log.Printf("Sandbox health server starting on port %d", port)
	log.Printf("Health endpoint: http://0.0.0.0:%d/sandbox_health", port)

	// Start server
	if err := server.ListenAndServe(); err != nil {
		log.Fatalf("Sandbox health server error: %v", err)
	}
}
