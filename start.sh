#!/bin/bash
# Start both the API backend and the UI frontend for the Cost Efficiency Score app.
#
# Usage: ./start.sh [--profile PROFILE_NAME]
#
# Prerequisites:
#   - pip3 install fastapi uvicorn boto3
#   - cd ui && npm install
#   - AWS credentials configured (env vars, ~/.aws/credentials, or IAM role)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UVICORN_PATH="${HOME}/Library/Python/3.9/bin/uvicorn"

# Fall back to uvicorn on PATH if the above doesn't exist
if [ ! -f "$UVICORN_PATH" ]; then
  UVICORN_PATH="uvicorn"
fi

echo "Starting Cost Efficiency Score application..."
echo "============================================="
echo ""

# Start the API backend
echo "[1/2] Starting API server on http://localhost:8000 ..."
cd "$SCRIPT_DIR"
"$UVICORN_PATH" api.main:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!

# Give the API a moment to start
sleep 2

# Start the UI frontend
echo "[2/2] Starting UI on http://localhost:3000 ..."
cd "$SCRIPT_DIR/ui"
npm run dev &
UI_PID=$!

echo ""
echo "============================================="
echo "Application running:"
echo "  UI:  http://localhost:3000"
echo "  API: http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers."
echo "============================================="

# Cleanup on exit
cleanup() {
  echo ""
  echo "Shutting down..."
  # Kill process groups to catch uvicorn's reload child processes
  kill -- -$API_PID 2>/dev/null || kill $API_PID 2>/dev/null || true
  kill -- -$UI_PID 2>/dev/null || kill $UI_PID 2>/dev/null || true
  # Also kill anything still on the ports
  kill $(lsof -ti :8000) 2>/dev/null || true
  kill $(lsof -ti :3000) 2>/dev/null || true
  exit 0
}

trap cleanup SIGINT SIGTERM

# Wait for either process to exit
wait
