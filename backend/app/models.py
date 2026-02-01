from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from enum import Enum

class RiskLevel(str, Enum):
    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"

class SensorDataInput(BaseModel):
    """Data received from ESP32"""
    heart_rate: float = Field(..., ge=0, le=200, description="Heart rate in BPM")
    spo2: float = Field(..., ge=0, le=100, description="Blood oxygen saturation %")
    temperature: float = Field(..., ge=0, le=50, description="Temperature in Celsius")
    humidity: float = Field(..., ge=0, le=100, description="Environmental humidity %")
    air_quality: float = Field(..., ge=0, le=500, description="Air quality index")
    device_id: Optional[str] = Field(default="ESP32_001", description="Device identifier")

    class Config:
        json_schema_extra = {
            "example": {
                "heart_rate": 72.0,
                "spo2": 98.0,
                "temperature": 36.8,
                "humidity": 45.0,
                "air_quality": 85.0,
                "device_id": "ESP32_001"
            }
        }

class PredictionResponse(BaseModel):
    """ML Model prediction response"""
    risk_level: RiskLevel
    confidence: float = Field(..., ge=0, le=1, description="Model confidence score")
    risk_score: float = Field(..., ge=0, le=1, description="Raw risk probability")
    recommendations: List[str]
    timestamp: datetime

class SensorDataResponse(BaseModel):
    """Response after storing sensor data"""
    id: int
    heart_rate: float
    spo2: float
    temperature: float
    humidity: float
    air_quality: float
    risk_level: RiskLevel
    risk_score: float
    device_id: str
    timestamp: datetime
    is_critical: bool

class HealthStatus(BaseModel):
    """Current health status summary"""
    current_vitals: SensorDataInput
    prediction: PredictionResponse
    alerts: List[str]
    status: str

class HistoricalData(BaseModel):
    """Historical data for charts"""
    timestamps: List[str]
    heart_rate: List[float]
    spo2: List[float]
    temperature: List[float]
    risk_scores: List[float]

class SystemStats(BaseModel):
    """System statistics"""
    total_readings: int
    high_risk_count: int
    moderate_risk_count: int
    low_risk_count: int
    last_updated: datetime
    device_status: str
    uptime_hours: float