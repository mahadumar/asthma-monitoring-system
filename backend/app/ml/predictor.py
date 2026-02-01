import joblib
import xgboost as xgb
import numpy as np
import pandas as pd
from typing import Dict, Tuple, List
import os
from pathlib import Path

class HealthPredictor:
    """XGBoost-based health risk predictor"""
    
    def __init__(self, model_path: str = None, scaler_path: str = None):
        # Get the ML directory path
        ml_dir = Path(__file__).parent
        
        # Load model
        if model_path is None:
            model_path = ml_dir / "xgb_model.pkl"
        
        if scaler_path is None:
            scaler_path = ml_dir / "scaler.joblib"
        
        try:
            self.model = joblib.load(model_path)
            self.scaler = joblib.load(scaler_path)
            print(f"✅ ML Model loaded from: {model_path}")
            print(f"✅ Scaler loaded from: {scaler_path}")
        except Exception as e:
            print(f"❌ Error loading model: {e}")
            raise
        
        # Feature names (must match training data)
        self.feature_names = [
            'heart_rate', 'spo2', 'temperature', 
            'humidity', 'air_quality'
        ]
        
        # Risk thresholds (from training)
        self.risk_thresholds = {
            'low': 0.33,
            'moderate': 0.66
        }
    
    def preprocess_data(self, sensor_data: Dict) -> np.ndarray:
        """Preprocess sensor data for prediction"""
        # Create DataFrame with proper feature order
        features = pd.DataFrame([{
            'heart_rate': sensor_data['heart_rate'],
            'spo2': sensor_data['spo2'],
            'temperature': sensor_data['temperature'],
            'humidity': sensor_data['humidity'],
            'air_quality': sensor_data['air_quality']
        }])
        
        # Scale features
        scaled_features = self.scaler.transform(features)
        return scaled_features
    
    def predict(self, sensor_data: Dict) -> Tuple[str, float, float, List[str]]:
        """
        Make prediction and return risk level, score, confidence, and recommendations
        
        Returns:
            Tuple[risk_level, risk_score, confidence, recommendations]
        """
        try:
            # Preprocess
            X = self.preprocess_data(sensor_data)
            
            # Get prediction probabilities
            proba = self.model.predict_proba(X)[0]
            
            # Get predicted class
            prediction = self.model.predict(X)[0]
            
            # Calculate risk score (weighted average of probabilities)
            # Assuming classes are [0: Low, 1: Moderate, 2: High]
            risk_score = (proba[0] * 0.0 + proba[1] * 0.5 + proba[2] * 1.0)
            
            # Determine risk level
            if prediction == 2 or risk_score >= self.risk_thresholds['moderate']:
                risk_level = "High"
            elif prediction == 1 or risk_score >= self.risk_thresholds['low']:
                risk_level = "Moderate"
            else:
                risk_level = "Low"
            
            # Confidence is the probability of the predicted class
            confidence = float(np.max(proba))
            
            # Generate recommendations
            recommendations = self._generate_recommendations(sensor_data, risk_level)
            
            return risk_level, float(risk_score), confidence, recommendations
            
        except Exception as e:
            print(f"❌ Prediction error: {e}")
            # Fallback to rule-based system
            return self._rule_based_prediction(sensor_data)
    
    def _rule_based_prediction(self, sensor_data: Dict) -> Tuple[str, float, float, List[str]]:
        """Fallback rule-based prediction if ML model fails"""
        critical_count = 0
        warning_count = 0
        
        # Check heart rate
        if sensor_data['heart_rate'] > 100 or sensor_data['heart_rate'] < 60:
            critical_count += 1
        elif sensor_data['heart_rate'] > 90 or sensor_data['heart_rate'] < 65:
            warning_count += 1
        
        # Check SpO2
        if sensor_data['spo2'] < 95:
            critical_count += 1
        elif sensor_data['spo2'] < 97:
            warning_count += 1
        
        # Check temperature
        if sensor_data['temperature'] > 37.8 or sensor_data['temperature'] < 36.0:
            critical_count += 1
        elif sensor_data['temperature'] > 37.5 or sensor_data['temperature'] < 36.2:
            warning_count += 1
        
        # Check air quality
        if sensor_data['air_quality'] < 50:
            critical_count += 1
        elif sensor_data['air_quality'] < 70:
            warning_count += 1
        
        # Determine risk
        if critical_count >= 2:
            risk_level = "High"
            risk_score = 0.8
        elif critical_count >= 1 or warning_count >= 2:
            risk_level = "Moderate"
            risk_score = 0.5
        else:
            risk_level = "Low"
            risk_score = 0.2
        
        confidence = 0.75  # Lower confidence for rule-based
        recommendations = self._generate_recommendations(sensor_data, risk_level)
        
        return risk_level, risk_score, confidence, recommendations
    
    def _generate_recommendations(self, sensor_data: Dict, risk_level: str) -> List[str]:
        """Generate health recommendations based on sensor data"""
        recommendations = []
        
        # Heart rate recommendations
        if sensor_data['heart_rate'] > 100:
            recommendations.append("⚠️ Elevated heart rate detected. Rest and monitor closely.")
        elif sensor_data['heart_rate'] < 60:
            recommendations.append("⚠️ Low heart rate detected. Consult healthcare provider.")
        
        # SpO2 recommendations
        if sensor_data['spo2'] < 95:
            recommendations.append("🚨 Low oxygen saturation. Seek immediate medical attention!")
        elif sensor_data['spo2'] < 97:
            recommendations.append("⚠️ Oxygen levels slightly low. Monitor breathing.")
        
        # Temperature recommendations
        if sensor_data['temperature'] > 37.8:
            recommendations.append("🌡️ Fever detected. Consider fever-reducing medication.")
        elif sensor_data['temperature'] < 36.0:
            recommendations.append("🌡️ Low body temperature. Keep warm and monitor.")
        
        # Air quality recommendations
        if sensor_data['air_quality'] < 70:
            recommendations.append("💨 Poor air quality. Improve ventilation or use air purifier.")
        
        # Humidity recommendations
        if sensor_data['humidity'] > 70:
            recommendations.append("💧 High humidity. Use dehumidifier for comfort.")
        elif sensor_data['humidity'] < 30:
            recommendations.append("💧 Low humidity. Consider using humidifier.")
        
        # General recommendations based on risk
        if risk_level == "High":
            recommendations.append("🚨 HIGH RISK: Contact healthcare provider immediately!")
        elif risk_level == "Moderate":
            recommendations.append("⚠️ MODERATE RISK: Monitor vitals every 15 minutes.")
        else:
            recommendations.append("✅ All vitals within normal range. Continue monitoring.")
        
        return recommendations if recommendations else ["✅ All vitals normal. Stay healthy!"]

# Singleton instance
_predictor_instance = None

def get_predictor() -> HealthPredictor:
    """Get or create predictor instance"""
    global _predictor_instance
    if _predictor_instance is None:
        _predictor_instance = HealthPredictor()
    return _predictor_instance