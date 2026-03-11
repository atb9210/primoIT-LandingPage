# Trico Rosmarinus - Backend API Integration

## 🚀 Branch: `feature/backend-api-integration`

### **Novità:**
- ✅ Backend FastAPI integrato
- ✅ API Worldfilia funzionante
- ✅ Frontend + Backend in un container
- ✅ Deployment Dokploy ready

### **📁 Struttura:**
```
├── index.html (frontend statico)
├── backend/
│   ├── main.py (API FastAPI)
│   └── requirements.txt
├── Dockerfile (unico container)
└── .dockerignore
```

### **🔧 Come Funziona:**

#### **1. Backend API (`/api/order`)**
- Riceve dati dal frontend
- Chiama API Worldfilia
- Ritorna risposta JSON
- Logging completo

#### **2. Frontend Integration**
- Form chiama `/api/order` (stesso dominio)
- Loading state durante chiamata
- Success message con order ID
- Fallback se API down

#### **3. Docker Container**
- Nginx porta 80 (frontend)
- FastAPI porta 8000 (backend)
- Proxy `/api/*` → backend
- Health check automatico

### **🚀 Deployment Dokploy:**

#### **1. Build Locale:**
```bash
docker build -t trico-backend .
docker run -p 80:80 trico-backend
```

#### **2. Deploy Dokploy:**
1. Push su GitHub
2. Dokploy → Import Project
3. Seleziona branch `feature/backend-api-integration`
4. Deploy automatico

### **📊 API Endpoints:**

#### **POST /api/order**
```json
{
  "name": "Mario Rossi",
  "phone": "3331234567",
  "address": "Via Roma 1, Milano",
  "aff_sub1": "trico_1234567890_abc123",
  "aff_sub2": "https://tuodominio.com"
}
```

Response:
```json
{
  "success": true,
  "order_id": "trico_1234567890_abc123",
  "message": "Order processed successfully"
}
```

#### **GET /health**
```json
{
  "status": "healthy"
}
```

#### **GET /api/stats**
```json
{
  "service": "Trico Rosmarinus API",
  "uptime": "Running",
  "version": "1.0.0"
}
```

### **🔍 Testing:**

#### **1. Frontend Test:**
- Apri `http://localhost`
- Compila form
- Controlla console per API call

#### **2. Backend Test:**
- `curl http://localhost/api/stats`
- `curl -X POST http://localhost/api/order -d '{"name":"Test","phone":"123","address":"Test"}'`

### **🛡️ Sicurezza:**
- ✅ API key nascosta nel backend
- ✅ Validazione input server-side
- ✅ Error handling graceful
- ✅ Logging per debug

### **📱 Mobile Ready:**
- ✅ Responsive design mantenuto
- ✅ API calls funzionanti su mobile
- ✅ Loading states ottimizzati

### **🔄 Rollback:**
Se qualcosa non funziona:
```bash
git checkout main
git push origin main
```

### **🎯 Next Steps:**
1. Test locale completo
2. Deploy Dokploy test
3. Monitoraggio logs
4. Facebook pixel integration (futuro)

---

**Status:** 🟢 Ready for Testing
