# PrimoIT — frontend (landing + shop) + backend FastAPI in un solo container
FROM python:3.11-slim

# Dipendenze di sistema
RUN apt-get update && apt-get install -y \
    nginx \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Backend ──
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ /app/

# Variabili (override in Dokploy)
ENV ENVIRONMENT=production
ENV LOG_LEVEL=INFO
ENV ADMIN_USER=admin
ENV ADMIN_PASS=cambia-questa-password
ENV DB_PATH=/app/data/primoit.db

# Cartella dati SQLite. La persistenza è data SOLO dal bind mount del compose
# (../files/data:/app/data). NIENTE `VOLUME` qui: un volume anonimo verrebbe
# ricreato da Docker/Dokploy a ogni deploy, perdendo i dati (era il bug dei deal spariti).
RUN mkdir -p /app/data

# ── Frontend ── (mantiene la struttura: landing/ e shop/ restano sorelle,
# cosi i path relativi sono identici al locale, incl. shop -> ../landing/images)
COPY landing/ /var/www/html/landing/
COPY shop/ /var/www/html/shop/

# Config nginx (serve i file statici + proxy /api/ -> backend)
COPY nginx.conf /etc/nginx/sites-available/default
RUN ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default \
    && mkdir -p /var/log/nginx

# Avvio (backend + nginx)
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/health || exit 1
CMD ["/start.sh"]
