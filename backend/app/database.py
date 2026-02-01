from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./health_monitoring.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models
class SensorReading(Base):
    __tablename__ = "sensor_readings"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True, default="ESP32_001")
    heart_rate = Column(Float, nullable=False)
    spo2 = Column(Float, nullable=False)
    temperature = Column(Float, nullable=False)
    humidity = Column(Float, nullable=False)
    air_quality = Column(Float, nullable=False)
    risk_level = Column(String, nullable=False)
    risk_score = Column(Float, nullable=False)
    is_critical = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

class Alert(Base):
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True)
    alert_type = Column(String, nullable=False)  # CRITICAL, WARNING, INFO
    message = Column(String, nullable=False)
    vital_name = Column(String, nullable=True)
    vital_value = Column(Float, nullable=True)
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)

class SystemLog(Base):
    __tablename__ = "system_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, nullable=False)  # DATA_RECEIVED, PREDICTION, ERROR
    message = Column(String, nullable=False)
    device_id = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

# Database initialization
def init_db():
    """Create all tables"""
    Base.metadata.create_all(bind=engine)
    print("✅ Database initialized successfully!")

def get_db():
    """Dependency for getting DB session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Utility functions
def create_sensor_reading(db, data: dict):
    """Create new sensor reading"""
    reading = SensorReading(**data)
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading

def get_latest_readings(db, device_id: str = None, limit: int = 100):
    """Get latest sensor readings"""
    query = db.query(SensorReading)
    if device_id:
        query = query.filter(SensorReading.device_id == device_id)
    return query.order_by(SensorReading.timestamp.desc()).limit(limit).all()

def create_alert(db, device_id: str, alert_type: str, message: str, vital_name: str = None, vital_value: float = None):
    """Create new alert"""
    alert = Alert(
        device_id=device_id,
        alert_type=alert_type,
        message=message,
        vital_name=vital_name,
        vital_value=vital_value
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert

def get_unresolved_alerts(db, device_id: str = None):
    """Get unresolved alerts"""
    query = db.query(Alert).filter(Alert.is_resolved == False)
    if device_id:
        query = query.filter(Alert.device_id == device_id)
    return query.order_by(Alert.created_at.desc()).all()

def log_system_event(db, event_type: str, message: str, device_id: str = None):
    """Log system event"""
    log = SystemLog(event_type=event_type, message=message, device_id=device_id)
    db.add(log)
    db.commit()
    return log