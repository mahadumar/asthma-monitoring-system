from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List
import os

from ..models import (
    SensorDataInput, SensorDataResponse, HistoricalData, 
    SystemStats, RiskLevel
)
from ..database import (
    get_db, create_sensor_reading, get_latest_readings,
    create_alert, get_unresolved_alerts, log_system_event,
    SensorReading
)
from ..ml.predictor import get_predictor

router = APIRouter(prefix="/api/sensor-data", tags=["Sensor Data"])

# Get ML predictor
predictor = get_predictor()

@router.post("/", response_model=SensorDataResponse)
async def receive_sensor_data(
    data: SensorDataInput,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Receive sensor data from ESP32, run ML prediction, and store in database
    """
    try:
        # Convert to dict for ML prediction
        sensor_dict = {
            "heart_rate": data.heart_rate,
            "spo2": data.spo2,
            "temperature": data.temperature,
            "humidity": data.humidity,
            "air_quality": data.air_quality
        }
        
        # Get ML prediction
        risk_level, risk_score, confidence, recommendations = predictor.predict(sensor_dict)
        
        # Determine if critical
        is_critical = (risk_level == "High")
        
        # Store in database
        db_data = {
            "device_id": data.device_id,
            "heart_rate": data.heart_rate,
            "spo2": data.spo2,
            "temperature": data.temperature,
            "humidity": data.humidity,
            "air_quality": data.air_quality,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "is_critical": is_critical,
            "timestamp": datetime.utcnow()
        }
        
        reading = create_sensor_reading(db, db_data)

        # 🆕 ADD THIS: Auto-cleanup old data (keep only last 24 hours)
        cleanup_cutoff = datetime.utcnow() - timedelta(hours=24)
        old_count = db.query(SensorReading).filter(
            SensorReading.timestamp < cleanup_cutoff
        ).delete()
        if old_count > 0:
            db.commit()
            print(f"🗑️ Cleaned up {old_count} old readings")
        
        # Create alert if critical
        if is_critical:
            background_tasks.add_task(
                create_alert,
                db=db,
                device_id=data.device_id,
                alert_type="CRITICAL",
                message=f"High risk detected! Risk score: {risk_score:.2f}",
                vital_name="risk_level",
                vital_value=risk_score
            )
        
        # Log event
        background_tasks.add_task(
            log_system_event,
            db=db,
            event_type="DATA_RECEIVED",
            message=f"Sensor data received - Risk: {risk_level}",
            device_id=data.device_id
        )
        
        return SensorDataResponse(
            id=reading.id,
            heart_rate=reading.heart_rate,
            spo2=reading.spo2,
            temperature=reading.temperature,
            humidity=reading.humidity,
            air_quality=reading.air_quality,
            risk_level=reading.risk_level,
            risk_score=reading.risk_score,
            device_id=reading.device_id,
            timestamp=reading.timestamp,
            is_critical=reading.is_critical
        )
        
    except Exception as e:
        log_system_event(
            db=db,
            event_type="ERROR",
            message=f"Error processing sensor data: {str(e)}",
            device_id=data.device_id
        )
        raise HTTPException(status_code=500, detail=f"Error processing data: {str(e)}")

@router.get("/latest", response_model=SensorDataResponse)
async def get_latest_reading(
    device_id: str = "ESP32_001",
    db: Session = Depends(get_db)
):
    """Get the most recent sensor reading"""
    readings = get_latest_readings(db, device_id=device_id, limit=1)
    
    if not readings:
        raise HTTPException(status_code=404, detail="No readings found")
    
    reading = readings[0]
    return SensorDataResponse(
        id=reading.id,
        heart_rate=reading.heart_rate,
        spo2=reading.spo2,
        temperature=reading.temperature,
        humidity=reading.humidity,
        air_quality=reading.air_quality,
        risk_level=reading.risk_level,
        risk_score=reading.risk_score,
        device_id=reading.device_id,
        timestamp=reading.timestamp,
        is_critical=reading.is_critical
    )

@router.get("/history", response_model=HistoricalData)
async def get_historical_data(
    device_id: str = "ESP32_001",
    hours: int = 24,
    db: Session = Depends(get_db)
):
    """Get historical sensor data for charts"""
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    readings = db.query(SensorReading).filter(
        SensorReading.device_id == device_id,
        SensorReading.timestamp >= cutoff_time
    ).order_by(SensorReading.timestamp.asc()).all()
    
    if not readings:
        return HistoricalData(
            timestamps=[],
            heart_rate=[],
            spo2=[],
            temperature=[],
            risk_scores=[]
        )
    
    return HistoricalData(
        timestamps=[r.timestamp.strftime("%H:%M:%S") for r in readings],
        heart_rate=[r.heart_rate for r in readings],
        spo2=[r.spo2 for r in readings],
        temperature=[r.temperature for r in readings],
        risk_scores=[r.risk_score for r in readings]
    )

@router.get("/stats", response_model=SystemStats)
async def get_system_stats(
    device_id: str = "ESP32_001",
    db: Session = Depends(get_db)
):
    """Get system statistics"""
    # Get all readings for this device
    all_readings = db.query(SensorReading).filter(
        SensorReading.device_id == device_id
    ).all()
    
    if not all_readings:
        return SystemStats(
            total_readings=0,
            high_risk_count=0,
            moderate_risk_count=0,
            low_risk_count=0,
            last_updated=datetime.utcnow(),
            device_status="No Data",
            uptime_hours=0.0
        )
    
    # Count risk levels
    high_risk = sum(1 for r in all_readings if r.risk_level == "High")
    moderate_risk = sum(1 for r in all_readings if r.risk_level == "Moderate")
    low_risk = sum(1 for r in all_readings if r.risk_level == "Low")
    
    # Calculate uptime
    first_reading = min(r.timestamp for r in all_readings)
    uptime = (datetime.utcnow() - first_reading).total_seconds() / 3600
    
    # Check last reading time
    last_reading = max(r.timestamp for r in all_readings)
    time_since_last = (datetime.utcnow() - last_reading).total_seconds()
    device_status = "Online" if time_since_last < 60 else "Offline"
    
    return SystemStats(
        total_readings=len(all_readings),
        high_risk_count=high_risk,
        moderate_risk_count=moderate_risk,
        low_risk_count=low_risk,
        last_updated=last_reading,
        device_status=device_status,
        uptime_hours=round(uptime, 2)
    )

@router.get("/alerts")
async def get_alerts(
    device_id: str = "ESP32_001",
    db: Session = Depends(get_db)
):
    """Get unresolved alerts"""
    alerts = get_unresolved_alerts(db, device_id=device_id)
    return {
        "count": len(alerts),
        "alerts": [
            {
                "id": a.id,
                "type": a.alert_type,
                "message": a.message,
                "vital_name": a.vital_name,
                "vital_value": a.vital_value,
                "created_at": a.created_at.isoformat()
            }
            for a in alerts
        ]
    }