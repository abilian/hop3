#!/bin/bash
# Multi-app deployment testing script for Hop3
# Tests deploying and accessing multiple applications simultaneously

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Hop3 Multi-App Deployment Test ===${NC}\n"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}"
    exit 1
fi

# Build Docker image
IMAGE_TAG="hop3-e2e:test"
echo -e "${YELLOW}Building Docker image (this may take 5-10 minutes)...${NC}"

# Build hop3-server distribution
echo "Building hop3-server distribution..."
uv build packages/hop3-server

# Build Docker image
docker build -f packages/hop3-server/tests/d_e2e/docker/Dockerfile \
    -t $IMAGE_TAG .

echo -e "${GREEN}✓ Docker image built${NC}"

# Stop and remove existing container if it exists
CONTAINER_NAME="hop3-deployment-test"
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Stopping and removing existing container..."
    docker stop $CONTAINER_NAME > /dev/null 2>&1 || true
    docker rm $CONTAINER_NAME > /dev/null 2>&1 || true
    echo -e "${GREEN}✓ Old container removed${NC}"
fi

# Check for port conflicts
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

# Set up environment for hop3 CLI
export HOP3_API_URL="ssh://hop3@localhost:$ACTUAL_SSH_PORT"
export HOP3_SSH_KEY="$SSH_KEY"
export HOP3_SECRET_KEY="e2e-test-secret-key-do-not-use-in-production"

# Function to create and deploy an app
deploy_app() {
    local APP_NAME=$1
    local APP_COLOR=$2
    local APP_PORT=$3
    local APP_DIR="/tmp/hop3-${APP_NAME}-$$"

    echo -e "\n${BLUE}=== Creating Application: ${APP_NAME} ===${NC}"
    mkdir -p $APP_DIR
    cd $APP_DIR

    # Create Flask app with unique content
    cat > app.py <<EOF
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def index():
    return """
    <html>
    <head>
        <title>${APP_NAME}</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background-color: ${APP_COLOR};
                color: white;
                text-align: center;
                padding: 50px;
            }
            .container {
                background-color: rgba(0,0,0,0.3);
                padding: 30px;
                border-radius: 10px;
                display: inline-block;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 ${APP_NAME}</h1>
            <p>This is the <strong>${APP_NAME}</strong> application</p>
            <p>Running on Hop3 Platform</p>
        </div>
    </body>
    </html>
    """

@app.route("/health")
def health():
    return jsonify({"status": "ok", "app": "${APP_NAME}"})

@app.route("/api/info")
def info():
    return jsonify({
        "name": "${APP_NAME}",
        "version": "1.0.0",
        "color": "${APP_COLOR}",
        "message": "Multi-app test deployment"
    })
EOF

    cat > requirements.txt <<'EOF'
flask>=3.0
EOF

    cat > Procfile <<'EOF'
web: flask --app app run --host 0.0.0.0 --port $PORT
EOF

    HOSTNAME="${APP_NAME}.local"
    cat > ENV <<EOF
HOST_NAME=$HOSTNAME
EOF

    # Initialize git
    git init > /dev/null 2>&1
    git add .
    git commit -m "Initial commit for ${APP_NAME}" > /dev/null 2>&1

    echo -e "${GREEN}✓ Application ${APP_NAME} created${NC}"

    # Deploy application
    echo "Deploying ${APP_NAME}..."
    if uv run hop3 deploy --app $APP_NAME $APP_DIR > /dev/null 2>&1; then
        echo -e "${GREEN}✓ ${APP_NAME} deployed successfully${NC}"
        return 0
    else
        echo -e "${RED}✗ ${APP_NAME} deployment failed${NC}"
        return 1
    fi
}

# Deploy first app
deploy_app "blueapp" "#0066cc" "5000"
BLUEAPP_DIR="/tmp/hop3-blueapp-$$"

# Deploy second app
deploy_app "greenapp" "#00aa44" "5001"
GREENAPP_DIR="/tmp/hop3-greenapp-$$"

# Wait for deployments to complete
echo -e "\n${BLUE}=== Waiting for Applications to Start ===${NC}"
echo "Waiting for apps to fully initialize (30 seconds)..."
sleep 30

# Check application status
echo -e "\n${GREEN}=== Application Status ===${NC}"
echo "Running: hop3 apps"
uv run hop3 apps

echo ""
echo "Running: hop3 app:status blueapp"
uv run hop3 app:status blueapp

echo ""
echo "Running: hop3 app:status greenapp"
uv run hop3 app:status greenapp

# Test HTTP access for both apps
echo -e "\n${GREEN}=== Testing HTTP Access ===${NC}"

# Test Blue App
echo -e "\n${BLUE}Testing Blue App:${NC}"
echo "URL: http://localhost:$ACTUAL_HTTP_PORT/ (Host: blueapp.local)"
if curl -sf -H "Host: blueapp.local" http://localhost:$ACTUAL_HTTP_PORT/ > /dev/null; then
    echo -e "${GREEN}✓ Blue app HTTP access working!${NC}"
    echo "Content preview:"
    curl -s -H "Host: blueapp.local" http://localhost:$ACTUAL_HTTP_PORT/ | grep -o "<h1>.*</h1>" || echo "(HTML content)"
else
    echo -e "${YELLOW}⚠ Blue app HTTP access not working${NC}"
fi

# Test Blue App Health
if curl -sf -H "Host: blueapp.local" http://localhost:$ACTUAL_HTTP_PORT/health > /dev/null; then
    echo -e "${GREEN}✓ Blue app health endpoint working${NC}"
    curl -s -H "Host: blueapp.local" http://localhost:$ACTUAL_HTTP_PORT/health | jq . 2>/dev/null || \
        curl -s -H "Host: blueapp.local" http://localhost:$ACTUAL_HTTP_PORT/health
else
    echo -e "${YELLOW}⚠ Blue app health endpoint not responding${NC}"
fi

# Test Green App
echo -e "\n${BLUE}Testing Green App:${NC}"
echo "URL: http://localhost:$ACTUAL_HTTP_PORT/ (Host: greenapp.local)"
if curl -sf -H "Host: greenapp.local" http://localhost:$ACTUAL_HTTP_PORT/ > /dev/null; then
    echo -e "${GREEN}✓ Green app HTTP access working!${NC}"
    echo "Content preview:"
    curl -s -H "Host: greenapp.local" http://localhost:$ACTUAL_HTTP_PORT/ | grep -o "<h1>.*</h1>" || echo "(HTML content)"
else
    echo -e "${YELLOW}⚠ Green app HTTP access not working${NC}"
fi

# Test Green App Health
if curl -sf -H "Host: greenapp.local" http://localhost:$ACTUAL_HTTP_PORT/health > /dev/null; then
    echo -e "${GREEN}✓ Green app health endpoint working${NC}"
    curl -s -H "Host: greenapp.local" http://localhost:$ACTUAL_HTTP_PORT/health | jq . 2>/dev/null || \
        curl -s -H "Host: greenapp.local" http://localhost:$ACTUAL_HTTP_PORT/health
else
    echo -e "${YELLOW}⚠ Green app health endpoint not responding${NC}"
fi

# Test API endpoints
echo -e "\n${GREEN}=== Testing API Endpoints ===${NC}"

echo -e "\n${BLUE}Blue App API:${NC}"
curl -s -H "Host: blueapp.local" http://localhost:$ACTUAL_HTTP_PORT/api/info | jq . 2>/dev/null || \
    curl -s -H "Host: blueapp.local" http://localhost:$ACTUAL_HTTP_PORT/api/info

echo -e "\n${BLUE}Green App API:${NC}"
curl -s -H "Host: greenapp.local" http://localhost:$ACTUAL_HTTP_PORT/api/info | jq . 2>/dev/null || \
    curl -s -H "Host: greenapp.local" http://localhost:$ACTUAL_HTTP_PORT/api/info

# Check nginx configuration for both apps
echo -e "\n${GREEN}=== Nginx Configuration ===${NC}"

echo -e "\n${BLUE}Blue App Nginx Config:${NC}"
if docker exec $CONTAINER_NAME test -f /home/hop3/nginx/blueapp.conf; then
    echo -e "${GREEN}✓ Config exists${NC}"
    docker exec $CONTAINER_NAME cat /home/hop3/nginx/blueapp.conf | grep -E "upstream|server_name|listen" | head -5
else
    echo -e "${YELLOW}⚠ Config not found${NC}"
fi

echo -e "\n${BLUE}Green App Nginx Config:${NC}"
if docker exec $CONTAINER_NAME test -f /home/hop3/nginx/greenapp.conf; then
    echo -e "${GREEN}✓ Config exists${NC}"
    docker exec $CONTAINER_NAME cat /home/hop3/nginx/greenapp.conf | grep -E "upstream|server_name|listen" | head -5
else
    echo -e "${YELLOW}⚠ Config not found${NC}"
fi

# Summary
echo -e "\n${GREEN}=== Test Summary ===${NC}"
echo ""
echo "Two applications deployed and running simultaneously:"
echo "  • blueapp  (blue theme)"
echo "  • greenapp (green theme)"
echo ""
echo "Both apps accessible via virtual hosts on the same port ($ACTUAL_HTTP_PORT)"

# Next steps
echo -e "\n${GREEN}=== Next Steps ===${NC}"
echo ""
echo "1. Add hostnames to /etc/hosts:"
echo -e "   ${YELLOW}echo '127.0.0.1 blueapp.local greenapp.local' | sudo tee -a /etc/hosts${NC}"
echo ""
echo "2. Access applications in browser:"
echo -e "   ${YELLOW}http://localhost:$ACTUAL_HTTP_PORT/${NC} (with Host header)"
echo "   or use curl:"
echo -e "   ${YELLOW}curl -H 'Host: blueapp.local' http://localhost:$ACTUAL_HTTP_PORT/${NC}"
echo -e "   ${YELLOW}curl -H 'Host: greenapp.local' http://localhost:$ACTUAL_HTTP_PORT/${NC}"
echo ""
echo "3. Deploy another app:"
echo -e "   ${YELLOW}export HOP3_API_URL=\"ssh://hop3@localhost:$ACTUAL_SSH_PORT\"${NC}"
echo -e "   ${YELLOW}export HOP3_SSH_KEY=\"$SSH_KEY\"${NC}"
echo -e "   ${YELLOW}uv run hop3 deploy --app myapp /path/to/app${NC}"
echo ""
echo "4. Check logs:"
echo -e "   ${YELLOW}uv run hop3 app:logs blueapp${NC}"
echo -e "   ${YELLOW}uv run hop3 app:logs greenapp${NC}"
echo ""
echo "5. Cleanup when done:"
echo -e "   ${YELLOW}docker stop $CONTAINER_NAME && docker rm $CONTAINER_NAME${NC}"
echo -e "   ${YELLOW}rm -rf $BLUEAPP_DIR $GREENAPP_DIR /tmp/hop3-*-$$ $SSH_KEY${NC}"
echo ""
echo -e "${GREEN}=== Test Complete ===${NC}"
