from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import Dict

from ..models import SensorDataInput, PredictionResponse, RiskLevel
from ..ml.predictor import get_predictor

router = APIRouter(prefix="/api/predictions", tags=["ML Predictions"])

# Get ML predictor
predictor = get_predictor()

@router.post("/predict", response_model=PredictionResponse)
async def predict_health_risk(data: SensorDataInput):
    """
    Get ML prediction for health risk based on sensor data
    """
    try:
        # Convert to dict
        sensor_dict = {
            "heart_rate": data.heart_rate,
            "spo2": data.spo2,
            "temperature": data.temperature,
            "humidity": data.humidity,
            "air_quality": data.air_quality
        }
        
        # Get prediction
        risk_level, risk_score, confidence, recommendations = predictor.predict(sensor_dict)
        
        return PredictionResponse(
            risk_level=RiskLevel(risk_level),
            confidence=confidence,
            risk_score=risk_score,
            recommendations=recommendations,
            timestamp=datetime.utcnow()
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Prediction error: {str(e)}"
        )

@router.post("/batch-predict")
async def batch_predict(data_list: list[SensorDataInput]):
    """
    Batch prediction for multiple sensor readings
    """
    try:
        results = []
        
        for data in data_list:
            sensor_dict = {
                "heart_rate": data.heart_rate,
                "spo2": data.spo2,
                "temperature": data.temperature,
                "humidity": data.humidity,
                "air_quality": data.air_quality
            }
            
            risk_level, risk_score, confidence, recommendations = predictor.predict(sensor_dict)
            
            results.append({
                "device_id": data.device_id,
                "risk_level": risk_level,
                "risk_score": risk_score,
                "confidence": confidence,
                "recommendations": recommendations[:3]  # Top 3 recommendations
            })
        
        return {
            "count": len(results),
            "predictions": results
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Batch prediction error: {str(e)}"
        )

@router.get("/model-info")
async def get_model_info():
    """
    Get information about the ML model
    """
    try:
        return {
            "model_type": "XGBoost Classifier",
            "features": predictor.feature_names,
            "risk_levels": ["Low", "Moderate", "High"],
            "thresholds": predictor.risk_thresholds,
            "status": "operational",
            "version": "1.0.0"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving model info: {str(e)}"
        )