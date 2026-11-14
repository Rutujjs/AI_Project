# Production Deployment & Containerization Guide

This guide details how to transition the AI-Powered Enterprise ESG Sustainability Platform from local evaluation into an enterprise production environment.

---

## 1. Local vs. Production Architecture

| Component | Local Evaluation Mode | Enterprise Production Mode |
| :--- | :--- | :--- |
| **Process Manager** | PowerShell / Batch (`start_platform.ps1`) | Docker Compose / Kubernetes / Systemd |
| **Relational Database**| Embedded SQLite (`platform.db`) | Managed PostgreSQL 14+ with replication |
| **Vector Database** | Local persistent ChromaDB | Clustered ChromaDB / Qdrant / Milvus |
| **Web Server** | Python `http.server` (Port 5500) | Nginx / Caddy Reverse Proxy (Port 443 HTTPS) |
| **Service Communication**| Localhost ports (8000, 8001, 5500) | Private Docker bridge network with unified reverse proxy |
| **TLS / SSL** | Unencrypted HTTP | Strict HTTPS with Let's Encrypt / Enterprise PKI |
| **JWT Secrets** | Built-in development key | High-entropy 256-bit random secrets via Vault |

---

## 2. Docker Compose Production Blueprint

The platform can be containerized using a clean multi-service `docker-compose.yml`:

```yaml
version: '3.8'

services:
  # ─── 1. PostgreSQL Database ────────────────────────────────────────────────
  postgres:
    image: postgres:15-alpine
    container_name: esg-postgres
    restart: always
    environment:
      POSTGRES_DB: esg_enterprise
      POSTGRES_USER: esg_admin
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - esg-internal
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U esg_admin -d esg_enterprise"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ─── 2. Member 2 Policy Intelligence Microservice (Port 8000) ──────────────
  policy-backend:
    build:
      context: .
      dockerfile: Dockerfile.policy
    container_name: esg-policy-backend
    restart: always
    environment:
      PORT: 8000
      GEMINI_API_KEY: ${GEMINI_API_KEY}
    networks:
      - esg-internal
    expose:
      - "8000"

  # ─── 3. Core Platform Backend (Port 8001) ──────────────────────────────────
  platform-backend:
    build:
      context: .
      dockerfile: Dockerfile.platform
    container_name: esg-platform-backend
    restart: always
    environment:
      ENVIRONMENT: production
      SECRET_KEY: ${SECRET_KEY}
      DATABASE_URL: postgresql://esg_admin:${DB_PASSWORD}@postgres:5432/esg_enterprise
      GEMINI_API_KEY: ${GEMINI_API_KEY}
      MEMBER2_API_URL: http://policy-backend:8000
      HF_HUB_OFFLINE: "1"
      TRANSFORMERS_OFFLINE: "1"
    depends_on:
      postgres:
        condition: service_healthy
      policy-backend:
        condition: service_started
    volumes:
      - chroma_data:/app/chroma_db
      - upload_data:/app/uploads
    networks:
      - esg-internal
    expose:
      - "8001"

  # ─── 4. Unified Frontend & Nginx Reverse Proxy ─────────────────────────────
  nginx:
    image: nginx:alpine
    container_name: esg-gateway
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./integrated-frontend:/usr/share/nginx/html:ro
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - certs:/etc/ssl/certs:ro
    depends_on:
      - platform-backend
      - policy-backend
    networks:
      - esg-internal

volumes:
  postgres_data:
  chroma_data:
  upload_data:
  certs:

networks:
  esg-internal:
    driver: bridge
```

---

## 3. Reverse Proxy & Unified Routing (Nginx Configuration)

By configuring Nginx as a reverse proxy, the client only accesses a single origin (e.g. `https://esg.company.com`), eliminating CORS pre-flight latency:

```nginx
server {
    listen 80;
    server_name esg.company.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name esg.company.com;

    ssl_certificate /etc/ssl/certs/fullchain.pem;
    ssl_certificate_key /etc/ssl/certs/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    # Static Frontend Assets
    location / {
        root /usr/share/nginx/html;
        index login.html;
        try_files $uri $uri/ /login.html;
    }

    # Policy Intelligence Microservice (Port 8000)
    location /policy-api/ {
        proxy_pass http://policy-backend:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Core Platform & Intelligence Backend (Port 8001)
    location /api/ {
        proxy_pass http://platform-backend:8001/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /documents/ {
        proxy_pass http://platform-backend:8001/documents/;
        client_max_body_size 25M;
    }

    location /green/ {
        proxy_pass http://platform-backend:8001/green/;
    }
}
```

---

## 4. PostgreSQL Database Migration Steps

When switching from SQLite to PostgreSQL:

1. Create the production database and user:
   ```sql
   CREATE DATABASE esg_enterprise;
   CREATE USER esg_admin WITH ENCRYPTED PASSWORD 'your_strong_password';
   GRANT ALL PRIVILEGES ON DATABASE esg_enterprise TO esg_admin;
   ```
2. Update `.env`:
   ```env
   DATABASE_URL=postgresql://esg_admin:your_strong_password@localhost:5432/esg_enterprise
   ```
3. Initialize the schema using the built-in SQLAlchemy initializer:
   ```bash
   python -c "from app.platform.database import init_db; init_db()"
   ```
4. Verify table and trigger creation:
   ```sql
   \dt
   -- Verify: organizations, users, suppliers, supplier_evaluations, audit_logs, notifications, notification_reads
   ```

---

## 5. Backup & Disaster Recovery

### Relational Database Backup (PostgreSQL)
Schedule automated daily backups using `pg_dump`:
```bash
pg_dump -U esg_admin -d esg_enterprise -F c -f /backups/esg_$(date +%Y%m%d_%H%M%S).dump
```

### ChromaDB Vector Store Backup
Since ChromaDB uses persistent SQLite and index binary files, back up the complete directory:
```bash
tar -czf /backups/chroma_backup_$(date +%Y%m%d).tar.gz /app/chroma_db
```

### Audit Log Archival Policy
Because the `audit_logs` table is strictly append-only and immutable, compliance requires periodic cold storage export:
```sql
COPY audit_logs TO '/backups/compliance_audit_2026.csv' WITH (FORMAT CSV, HEADER);
```

