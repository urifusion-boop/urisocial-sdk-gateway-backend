# URI Gateway Backend Deployment Guide

Complete guide to deploy the URI Social Gateway API to Azure VM with Docker.

## 🎯 Overview

- **Backend API**: FastAPI + MongoDB + Beanie
- **Deployment**: Docker container on Azure VM
- **Domain**: `api-gateway.urisocial.com`
- **Frontend Domain**: `developers.urisocial.com`
- **Port**: 9006 (mapped to container port 80)

---

## 📋 Prerequisites

1. **Azure VM**: 20.9.131.143 (already provisioned)
2. **SSH Key**: `~/.ssh/urisocialprod_key.pem`
3. **Docker Hub**: uriteam/urisvc repository access
4. **Namecheap**: Domain management access
5. **GitHub**: Repository with Actions enabled

---

## 🌐 Part 1: Namecheap Domain Setup

### Step 1: Add A Record for API Gateway

1. **Login to Namecheap**:
   - Go to https://www.namecheap.com
   - Login to your account

2. **Navigate to Domain DNS**:
   - Dashboard → Domain List
   - Click "Manage" next to `urisocial.com`
   - Go to "Advanced DNS" tab

3. **Add A Record**:
   ```
   Type: A Record
   Host: api-gateway
   Value: 20.9.131.143
   TTL: Automatic
   ```

4. **Add A Record for Developers Portal** (if not exists):
   ```
   Type: A Record
   Host: developers
   Value: 20.9.131.143
   TTL: Automatic
   ```

5. **Save Changes**:
   - Click "Save All Changes"
   - DNS propagation takes 5-30 minutes

### Step 2: Verify DNS Propagation

```bash
# Check if DNS is propagated
nslookup api-gateway.urisocial.com

# Expected output:
# Name:    api-gateway.urisocial.com
# Address: 20.9.131.143
```

---

## 🖥️ Part 2: Server Setup (One-Time)

### Step 1: SSH into Azure VM

```bash
ssh -i ~/.ssh/urisocialprod_key.pem urisocialprod@20.9.131.143
```

### Step 2: Install Docker (if not installed)

```bash
# Update packages
sudo apt-get update

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify installation
docker --version
docker-compose --version
```

### Step 3: Create Docker Network (if not exists)

```bash
# Check if network exists
docker network ls | grep uritest-network

# If not exists, create it
docker network create uritest-network
```

### Step 4: Setup MongoDB (if not running)

**Option A: MongoDB in Docker (Recommended)**
```bash
# Create MongoDB container
docker run -d \
  --name mongodb \
  --network uritest-network \
  -p 27017:27017 \
  -v mongodb_data:/data/db \
  -e MONGO_INITDB_ROOT_USERNAME=admin \
  -e MONGO_INITDB_ROOT_PASSWORD=<STRONG_PASSWORD> \
  --restart always \
  mongo:latest

# Verify MongoDB is running
docker ps | grep mongodb
```

**Option B: MongoDB Atlas (Cloud)**
- Use MongoDB Atlas connection string in `.env.production`
- No local MongoDB setup needed

### Step 5: Setup Redis (if not running)

```bash
# Create Redis container
docker run -d \
  --name redis \
  --network uritest-network \
  -p 6379:6379 \
  --restart always \
  redis:latest

# Verify Redis is running
docker ps | grep redis
```

### Step 6: Create Production Environment File

```bash
# Create directory
mkdir -p ~/uri-gateway-backend
cd ~/uri-gateway-backend

# Create .env.production file
nano .env.production
```

**Paste this content** (update with real values):
```env
# MongoDB Database (Production)
MONGODB_URL=mongodb://admin:<PASSWORD>@mongodb:27017
DATABASE_NAME=uri_gateway_prod

# JWT
SECRET_KEY=<GENERATE_STRONG_SECRET_KEY_HERE>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Redis
REDIS_URL=redis://redis:6379

# CORS
FRONTEND_URL=https://developers.urisocial.com

# Environment
ENVIRONMENT=production

# API Keys
API_KEY_PREFIX=urisocial_
```

**Generate strong SECRET_KEY**:
```bash
# Run this to generate a secure key
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

### Step 7: Setup Nginx (Reverse Proxy)

```bash
# Install Nginx
sudo apt-get install -y nginx

# Create Nginx config for API Gateway
sudo nano /etc/nginx/sites-available/api-gateway.urisocial.com
```

**Paste this Nginx config**:
```nginx
server {
    listen 80;
    server_name api-gateway.urisocial.com;

    location / {
        proxy_pass http://localhost:9006;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
```

**Enable the site**:
```bash
# Create symbolic link
sudo ln -s /etc/nginx/sites-available/api-gateway.urisocial.com /etc/nginx/sites-enabled/

# Test Nginx config
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
```

### Step 8: Setup SSL with Let's Encrypt

```bash
# Install Certbot
sudo apt-get install -y certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d api-gateway.urisocial.com

# Follow prompts:
# - Enter email
# - Agree to terms
# - Choose to redirect HTTP to HTTPS (option 2)

# Verify auto-renewal
sudo certbot renew --dry-run
```

---

## 🚀 Part 3: GitHub Actions Setup

### Step 1: Add GitHub Secrets

Go to your GitHub repository:
```
Settings → Secrets and variables → Actions → New repository secret
```

**Add these secrets**:

1. **DOCKER_USERNAME**
   ```
   Value: uriteam
   ```

2. **DOCKER_PASSWORD**
   ```
   Value: <your-docker-hub-password>
   ```

3. **VM_IP_PROD**
   ```
   Value: 20.9.131.143
   ```

4. **SSH_PRIVATE_KEY_PROD**
   ```
   Value: <content of ~/.ssh/urisocialprod_key.pem>
   ```

   Get the key content:
   ```bash
   cat ~/.ssh/urisocialprod_key.pem
   ```
   Copy entire output including `-----BEGIN RSA PRIVATE KEY-----` and `-----END RSA PRIVATE KEY-----`

### Step 2: Push Code to GitHub

```bash
cd /Users/apple/Desktop/URI_Corrected/uri-social-gateway-backend

# Initialize git if not already
git init
git remote add origin <your-github-repo-url>

# Add all files
git add .
git commit -m "Initial commit: URI Gateway Backend with deployment setup"

# Push to main branch (will trigger deployment)
git push -u origin main
```

### Step 3: Monitor Deployment

1. Go to GitHub repository
2. Click "Actions" tab
3. Watch the deployment workflow
4. Both `build` and `deploy` jobs should complete successfully

---

## ✅ Part 4: Verification

### Step 1: Check Container Status

```bash
# SSH into VM
ssh -i ~/.ssh/urisocialprod_key.pem urisocialprod@20.9.131.143

# Check running containers
docker ps | grep uri-gateway

# Check container logs
docker logs uri-gateway.api.prod

# Should see:
# ✅ Connected to MongoDB: uri_gateway_prod
# INFO:     Uvicorn running on http://0.0.0.0:80
```

### Step 2: Test API Endpoints

```bash
# Test health endpoint (no SSL)
curl http://api-gateway.urisocial.com/health

# Expected: {"status":"healthy","service":"uri-social-gateway-api"}

# Test health endpoint (with SSL)
curl https://api-gateway.urisocial.com/health

# Test API docs
curl https://api-gateway.urisocial.com/docs

# Test auth endpoint
curl -X POST https://api-gateway.urisocial.com/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "testpassword123",
    "first_name": "Test",
    "last_name": "User"
  }'
```

### Step 3: Check MongoDB Connection

```bash
# SSH into VM
ssh -i ~/.ssh/urisocialprod_key.pem urisocialprod@20.9.131.143

# Connect to MongoDB
docker exec -it mongodb mongosh -u admin -p

# List databases
show dbs

# Should see: uri_gateway_prod

# Use database
use uri_gateway_prod

# List collections
show collections

# Should see: developers, api_keys, workspaces, etc.
```

---

## 🔄 Part 5: Updating/Redeploying

### Automatic Deployment (Recommended)

Just push to `main` branch:
```bash
git add .
git commit -m "Update backend"
git push origin main
```

GitHub Actions will automatically:
1. Build new Docker image
2. Push to Docker Hub
3. Deploy to Azure VM
4. Restart container

### Manual Deployment

```bash
# SSH into VM
ssh -i ~/.ssh/urisocialprod_key.pem urisocialprod@20.9.131.143

cd ~/uri-gateway-backend

# Pull latest image
docker pull uriteam/urisvc:urigatewayapiprod

# Restart container
docker-compose -p uri-gateway-backend-prod -f docker-compose.prod.yml down
docker-compose -p uri-gateway-backend-prod -f docker-compose.prod.yml up -d

# Check logs
docker logs -f uri-gateway.api.prod
```

---

## 🛠️ Troubleshooting

### Container won't start

```bash
# Check logs
docker logs uri-gateway.api.prod

# Check if port is already in use
sudo netstat -tulpn | grep 9006

# Restart container
docker restart uri-gateway.api.prod
```

### MongoDB connection failed

```bash
# Check MongoDB is running
docker ps | grep mongodb

# Check MongoDB logs
docker logs mongodb

# Test connection
docker exec -it uri-gateway.api.prod ping mongodb
```

### SSL certificate issues

```bash
# Renew certificate manually
sudo certbot renew

# Check certificate status
sudo certbot certificates
```

### Nginx issues

```bash
# Check Nginx status
sudo systemctl status nginx

# Check Nginx error logs
sudo tail -f /var/log/nginx/error.log

# Test config
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
```

---

## 📊 Architecture Diagram

```
Internet
   ↓
Namecheap DNS (api-gateway.urisocial.com → 20.9.131.143)
   ↓
Azure VM (20.9.131.143)
   ↓
Nginx (Port 80/443) → SSL Termination
   ↓
Docker Container (Port 9006:80)
   ├── FastAPI App (Uvicorn, 4 workers)
   ├── MongoDB (uritest-network)
   └── Redis (uritest-network)
```

---

## 🔐 Security Checklist

- [x] SSH access restricted to specific IP addresses
- [x] Strong MongoDB password
- [x] JWT secret is 64+ characters
- [x] SSL certificate installed (Let's Encrypt)
- [x] Environment variables secured (.env.production not in git)
- [x] Docker containers restart on failure
- [x] Firewall configured (only ports 80, 443, 22 open)
- [x] Regular backups of MongoDB data

---

## 📝 Environment URLs

- **Production API**: https://api-gateway.urisocial.com
- **API Docs**: https://api-gateway.urisocial.com/docs
- **Health Check**: https://api-gateway.urisocial.com/health
- **Developer Portal**: https://developers.urisocial.com

---

## 🆘 Support

If you encounter issues:
1. Check container logs: `docker logs uri-gateway.api.prod`
2. Check GitHub Actions workflow
3. Verify DNS with `nslookup api-gateway.urisocial.com`
4. Test MongoDB connection
5. Check Nginx logs: `sudo tail -f /var/log/nginx/error.log`
