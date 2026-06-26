#!/bin/bash
echo "Starting PrimoIT API..."

# Start FastAPI backend in background
cd /app
uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' &

# Wait for backend to start
sleep 3

# Test backend health
curl -f http://localhost:8000/health || echo "Health check failed, continuing anyway..."

echo "Starting nginx..."

# Start nginx in foreground
nginx -g "daemon off;"
