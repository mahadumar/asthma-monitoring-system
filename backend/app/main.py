from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import json
from datetime import datetime
from typing import List
import os
from dotenv import load_dotenv

from .database import init_db, get_db, SessionLocal
from .routes import sensor_data, predictions

# Load environment variables
load_dotenv()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"✅ WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print(f"❌ WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Error broadcasting: {e}")

manager = ConnectionManager()

# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting Health Monitoring System...")
    init_db()
    print("✅ Database initialized")
    yield
    # Shutdown
    print("🛑 Shutting down...")

# Create FastAPI app
app = FastAPI(
    title="IoT Health Monitoring System",
    description="Real-time health monitoring with ESP32 + ML predictions",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration - FIXED FOR DEVELOPMENT
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# Include routers
app.include_router(sensor_data.router)
app.include_router(predictions.router)

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "🏥 IoT Health Monitoring System API",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": {
            "sensor_data": "/api/sensor-data",
            "predictions": "/api/predictions",
            "docs": "/docs",
            "websocket": "/ws"
        }
    }

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "database": "connected",
        "ml_model": "loaded"
    }

# WebSocket endpoint for real-time updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Receive data from client
            data = await websocket.receive_text()
            
            # Parse and process
            try:
                message = json.loads(data)
                
                # Echo back with timestamp
                response = {
                    "type": "acknowledgment",
                    "message": "Data received",
                    "timestamp": datetime.utcnow().isoformat()
                }
                await websocket.send_json(response)
                
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON format"
                })
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# WebSocket broadcast endpoint (for testing)
@app.post("/broadcast")
async def broadcast_message(message: dict):
    """Broadcast message to all WebSocket clients"""
    await manager.broadcast(message)
    return {"status": "broadcasted", "connections": len(manager.active_connections)}

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Endpoint not found", "path": str(request.url)}
    )

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )

# Startup message
@app.on_event("startup")
async def startup_event():
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║                                                       ║
    ║     🏥 IoT Health Monitoring System Started 🏥      ║
    ║                                                       ║
    ║  Backend: FastAPI + XGBoost ML                       ║
    ║  Database: SQLite                                    ║
    ║  WebSocket: Enabled                                  ║
    ║  CORS: Enabled for Development                       ║
    ║                                                       ║
    ║  Access API docs: http://localhost:8000/docs         ║
    ║  WebSocket: ws://localhost:8000/ws                   ║
    ║                                                       ║
    ╚═══════════════════════════════════════════════════════╝
    """)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("API_PORT", 8000))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )