#!/bin/bash
# Manual deployment testing script for Hop3
# This script sets up a test environment and deploys a sample application

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Hop3 Manual Deployment Test ===${NC}\n"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}"
    exit 1
fi

# Build Docker image if it doesn't exist
IMAGE_TAG="hop3-e2e:test"
if ! docker image inspect $IMAGE_TAG > /dev/null 2>&1; then
    echo -e "${YELLOW}Building Docker image (this may take 5-10 minutes)...${NC}"

    # Build hop3-server distribution
    echo "Building hop3-server distribution..."
    uv build packages/hop3-server

    # Build Docker image
    docker build -f packages/hop3-server/tests/d_e2e/docker/Dockerfile \
        -t $IMAGE_TAG .

    echo -e "${GREEN}✓ Docker image built${NC}"
else
    echo -e "${GREEN}✓ Using existing Docker image${NC}"
fi

# Stop and remove existing container if it exists
CONTAINER_NAME="hop3-deployment-test"
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Stopping and removing existing container..."
    docker stop $CONTAINER_NAME > /dev/null 2>&1 || true
    docker rm $CONTAINER_NAME > /dev/null 2>&1 || true
    echo -e "${GREEN}✓ Old container removed${NC}"
fi

# Also check if ports are in use
if lsof -Pi :2222 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${YELLOW}Warning: Port 2222 is in use. Trying random port...${NC}"
    SSH_PORT=""
else
    SSH_PORT="-p 2222:22"
fi

if lsof -Pi :8080 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${YELLOW}Warning: Port 8080 is in use. Trying random port...${NC}"
    HTTP_PORT=""
else
    HTTP_PORT="-p 8080:80"
fi

if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${YELLOW}Warning: Port 8000 is in use. Trying random port...${NC}"
    API_PORT=""
else
    API_PORT="-p 8000:8000"
fi

# Start container
echo "Starting Hop3 container..."
docker run -d \
    --name $CONTAINER_NAME \
    $SSH_PORT \
    $HTTP_PORT \
    $API_PORT \
    $IMAGE_TAG

# Wait for services to start
echo "Waiting for services to initialize..."
sleep 5

# Check container is running
if ! docker ps | grep -q $CONTAINER_NAME; then
    echo -e "${RED}Error: Container failed to start${NC}"
    docker logs $CONTAINER_NAME
    exit 1
fi

# Get actual ports (in case random ports were assigned)
ACTUAL_SSH_PORT=$(docker port $CONTAINER_NAME 22 | cut -d: -f2)
ACTUAL_HTTP_PORT=$(docker port $CONTAINER_NAME 80 | cut -d: -f2)
ACTUAL_API_PORT=$(docker port $CONTAINER_NAME 8000 | cut -d: -f2)

# Get SSH key
SSH_KEY="/tmp/hop3-deployment-test-key"
docker exec $CONTAINER_NAME cat /home/hop3/.ssh/id_rsa > $SSH_KEY
chmod 600 $SSH_KEY

echo -e "\n${GREEN}=== Container Information ===${NC}"
echo "Container: $CONTAINER_NAME"
echo "SSH: ssh -i $SSH_KEY -p $ACTUAL_SSH_PORT hop3@localhost"
echo "HTTP: http://localhost:$ACTUAL_HTTP_PORT"
echo "API: http://localhost:$ACTUAL_API_PORT"

# Create test application
APP_NAME="testapp"
HOSTNAME="${APP_NAME}.local"
APP_DIR="/tmp/hop3-test-app-$$"

echo -e "\n${GREEN}=== Creating Test Application ===${NC}"
mkdir -p $APP_DIR
cd $APP_DIR

# Create Flask app
cat > app.py <<'EOF'
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def index():
    return "<h1>Hello from Hop3!</h1><p>This is a test application deployed manually.</p>"

@app.route("/health")
def health():
    return jsonify({"status": "ok", "app": "testapp"})

@app.route("/api/info")
def info():
    return jsonify({
        "name": "testapp",
        "version": "1.0.0",
        "message": "Deployed via manual script"
    })
EOF

cat > requirements.txt <<'EOF'
flask>=3.0
EOF

cat > Procfile <<'EOF'
web: flask --app app run --host 0.0.0.0 --port $PORT
EOF

cat > ENV <<EOF
HOST_NAME=$HOSTNAME
EOF

# Initialize git
git init > /dev/null
git add .
git commit -m "Initial commit" > /dev/null

# Create tarball
TARBALL="/tmp/${APP_NAME}-$$.tar.gz"
git archive --format=tar.gz -o $TARBALL HEAD

echo -e "${GREEN}✓ Test application created${NC}"

# Deploy application using hop3 CLI (via SSH/RPC)
echo -e "\n${GREEN}=== Deploying Application ===${NC}"

# Set up environment for hop3 CLI
export HOP3_API_URL="ssh://hop3@localhost:$ACTUAL_SSH_PORT"
export HOP3_SSH_KEY="$SSH_KEY"
export HOP3_SECRET_KEY="e2e-test-secret-key-do-not-use-in-production"

# Deploy using hop3 CLI
echo "Running: hop3 deploy --app $APP_NAME $APP_DIR"
if uv run hop3 deploy --app $APP_NAME $APP_DIR; then
    echo -e "${GREEN}✓ Deployment initiated${NC}"
else
    echo -e "${RED}✗ Deployment failed${NC}"
    echo "Note: You can also deploy manually from the host:"
    echo "  export HOP3_API_URL=\"ssh://hop3@localhost:$ACTUAL_SSH_PORT\""
    echo "  export HOP3_SSH_KEY=\"$SSH_KEY\""
    echo "  uv run hop3 deploy --app $APP_NAME $APP_DIR"
fi

# Wait for deployment
echo "Waiting for deployment to complete..."
sleep 15

# Check app status
echo -e "\n${GREEN}=== Application Status ===${NC}"
echo "Running: hop3 apps"
uv run hop3 apps || echo -e "${YELLOW}Could not list apps${NC}"
echo ""
echo "Running: hop3 app:status $APP_NAME"
uv run hop3 app:status $APP_NAME || echo -e "${YELLOW}Could not get app status${NC}"

# Check nginx configuration
echo -e "\n${GREEN}=== Nginx Configuration ===${NC}"
echo "Checking if nginx config exists..."
if docker exec $CONTAINER_NAME test -f /home/hop3/nginx/$APP_NAME.conf; then
    echo -e "${GREEN}✓ Nginx config exists${NC}"
    echo "Config content:"
    docker exec $CONTAINER_NAME cat /home/hop3/nginx/$APP_NAME.conf | head -20
else
    echo -e "${YELLOW}⚠ Nginx config not found${NC}"
fi

echo ""
echo "Checking nginx status..."
docker exec $CONTAINER_NAME systemctl is-active nginx 2>/dev/null || docker exec $CONTAINER_NAME service nginx status 2>/dev/null || echo -e "${YELLOW}⚠ Could not check nginx status (might be running via supervisor)${NC}"

echo ""
echo "Checking if nginx is listening on port 80..."
docker exec $CONTAINER_NAME netstat -tuln 2>/dev/null | grep :80 || echo -e "${YELLOW}⚠ Nginx might not be listening on port 80${NC}"

# Test HTTP access
echo -e "\n${GREEN}=== Testing HTTP Access ===${NC}"
echo "Testing: curl -H \"Host: $HOSTNAME\" http://localhost:$ACTUAL_HTTP_PORT/"

if curl -sf -H "Host: $HOSTNAME" http://localhost:$ACTUAL_HTTP_PORT/ > /dev/null; then
    echo -e "${GREEN}✓ HTTP access working!${NC}"
    echo ""
    echo "Response:"
    curl -s -H "Host: $HOSTNAME" http://localhost:$ACTUAL_HTTP_PORT/ | head -5
    echo ""
else
    echo -e "${YELLOW}⚠ HTTP access not working (this might be expected if nginx isn't properly configured)${NC}"
fi

# Test health endpoint
echo -e "\n${GREEN}=== Testing Health Endpoint ===${NC}"
if curl -sf -H "Host: $HOSTNAME" http://localhost:$ACTUAL_HTTP_PORT/health > /dev/null; then
    echo -e "${GREEN}✓ Health endpoint working${NC}"
    curl -s -H "Host: $HOSTNAME" http://localhost:$ACTUAL_HTTP_PORT/health | jq . || curl -s -H "Host: $HOSTNAME" http://localhost:$ACTUAL_HTTP_PORT/health
    echo ""
else
    echo -e "${YELLOW}⚠ Health endpoint not responding${NC}"
fi

# Instructions
echo -e "\n${GREEN}=== Next Steps ===${NC}"
echo ""
echo "1. Add hostname to /etc/hosts:"
echo -e "   ${YELLOW}echo '127.0.0.1 $HOSTNAME' | sudo tee -a /etc/hosts${NC}"
echo ""
echo "2. Access the application:"
echo -e "   ${YELLOW}curl http://localhost:$ACTUAL_HTTP_PORT/ -H 'Host: $HOSTNAME'${NC}"
echo "   or in browser: http://localhost:$ACTUAL_HTTP_PORT/ (with Host header)"
echo ""
echo "3. Deploy another app:"
echo -e "   ${YELLOW}export HOP3_API_URL=\"ssh://hop3@localhost:$ACTUAL_SSH_PORT\"${NC}"
echo -e "   ${YELLOW}export HOP3_SSH_KEY=\"$SSH_KEY\"${NC}"
echo -e "   ${YELLOW}uv run hop3 deploy --app myapp /path/to/app${NC}"
echo ""
echo "4. Check logs:"
echo -e "   ${YELLOW}uv run hop3 logs $APP_NAME${NC}"
echo ""
echo "5. SSH into container:"
echo -e "   ${YELLOW}ssh -i $SSH_KEY -p $ACTUAL_SSH_PORT hop3@localhost${NC}"
echo ""
echo "6. View nginx config:"
echo -e "   ${YELLOW}docker exec $CONTAINER_NAME cat /home/hop3/nginx/$APP_NAME.conf${NC}"
echo ""
echo "7. Cleanup when done:"
echo -e "   ${YELLOW}docker stop $CONTAINER_NAME && docker rm $CONTAINER_NAME${NC}"
echo -e "   ${YELLOW}rm -rf $APP_DIR $TARBALL $SSH_KEY${NC}"
echo ""
echo -e "${GREEN}=== Test Complete ===${NC}"
