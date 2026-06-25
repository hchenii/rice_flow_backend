"""
Yield prediction service — trains and runs 3 regression models.

Models compared:
  1. Linear Regression  — baseline, easy to explain
  2. Ridge Regression   — handles correlated farm features (L2)
  3. Lasso Regression   — auto feature selection (L1)

Metrics: R², MAE, RMSE  (same role as Silhouette/Inertia for clustering)
"""
import os
import numpy as np
import joblib
from pathlib import Path
from django.conf import settings

from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error

MODELS_DIR: Path = settings.MODELS_DIR

FEATURE_NAMES = [
    'area_ha', 'soil_ph', 'organic_matter', 'avg_temperature',
    'seasonal_rainfall', 'humidity', 'elevation_m',
    'flood_risk_enc',   # low=0, moderate=1, high=2
    'ecosystem_enc',    # lowland=0, upland=1
    'maturity_days', 'variety_avg_yield',
]

FLOOD_MAP = {'low': 0, 'moderate': 1, 'high': 2}
ECO_MAP   = {'lowland': 0, 'irrigated_lowland': 0, 'rainfed_lowland': 0,
             'upland': 1, 'highland': 1}


def encode_features(raw: dict) -> np.ndarray:
    return np.array([[
        float(raw.get('area_ha', 1.0)),
        float(raw.get('soil_ph', 6.0)),
        float(raw.get('organic_matter', 2.0)),
        float(raw.get('avg_temperature', 28.0)),
        float(raw.get('seasonal_rainfall', 2000)),
        float(raw.get('humidity', 75)),
        float(raw.get('elevation_m', 50)),
        FLOOD_MAP.get(str(raw.get('flood_risk', 'low')).lower(), 0),
        ECO_MAP.get(str(raw.get('ecosystem', 'lowland')).lower(), 0),
        float(raw.get('maturity_days', 113)),
        float(raw.get('variety_avg_yield', 5.0)),
    ]])


def _generate_training_data(n_samples: int = 800) -> tuple:
    """
    Synthetic dataset based on known agronomic relationships.
    Used until enough real YieldRecords accumulate.
    """
    rng = np.random.default_rng(42)

    area_ha          = rng.uniform(0.5, 5.0,   n_samples)
    soil_ph          = rng.uniform(5.0, 7.5,   n_samples)
    organic_matter   = rng.uniform(0.5, 4.0,   n_samples)
    avg_temp         = rng.uniform(24, 34,      n_samples)
    rainfall         = rng.uniform(1200, 3500,  n_samples)
    humidity         = rng.uniform(60, 90,      n_samples)
    elevation_m      = rng.uniform(0, 600,      n_samples)
    flood_risk_enc   = rng.integers(0, 3,       n_samples).astype(float)
    ecosystem_enc    = rng.integers(0, 2,       n_samples).astype(float)
    maturity_days    = rng.uniform(100, 130,    n_samples)
    variety_avg_y    = rng.uniform(4.0, 7.5,   n_samples)

    # Yield formula with agronomic weights + noise
    yield_t_ha = (
        variety_avg_y * 0.40
        + (soil_ph - 4) * 0.18
        + organic_matter * 0.12
        + np.clip((rainfall - 1200) / 1000, 0, 1) * 0.25
        - np.abs(avg_temp - 28) * 0.06
        + (1 - ecosystem_enc) * 0.20          # lowland slightly better
        - flood_risk_enc * 0.15
        - elevation_m / 2000
        + rng.normal(0, 0.25, n_samples)      # noise
    )
    yield_t_ha = np.clip(yield_t_ha, 1.5, 9.0)

    X = np.column_stack([
        area_ha, soil_ph, organic_matter, avg_temp,
        rainfall, humidity, elevation_m,
        flood_risk_enc, ecosystem_enc,
        maturity_days, variety_avg_y,
    ])
    return X, yield_t_ha


def _get_real_training_data():
    """Pull actual YieldRecord rows if available."""
    from apps.progress.models import YieldRecord
    from apps.farms.models import Farm
    from apps.environmental.models import EnvironmentalScan

    rows = (YieldRecord.objects
            .select_related('farm_cycle__farm', 'farm_cycle__variety')
            .filter(net_yield_kg__gt=0))

    X_rows, y_rows = [], []
    for yr in rows:
        cycle = yr.farm_cycle
        farm  = cycle.farm
        scans = EnvironmentalScan.objects.filter(farm=farm).order_by('-id').first()
        if not scans:
            continue
        area = float(farm.area_ha or 1.0)
        y_t_ha = (yr.net_yield_kg / 1000) / max(area, 0.1)
        X_rows.append([
            area,
            float(scans.soil_ph),
            float(scans.organic_matter),
            float(scans.avg_temperature),
            float(scans.seasonal_rainfall),
            float(scans.humidity),
            float(scans.elevation_m),
            FLOOD_MAP.get(scans.flood_risk, 0),
            ECO_MAP.get(farm.ecosystem, 0),
            float(cycle.variety.maturity_days),
            float(cycle.variety.avg_yield_t_ha),
        ])
        y_rows.append(y_t_ha)

    if len(X_rows) < 30:
        return None, None
    return np.array(X_rows), np.array(y_rows)


def train_all_models():
    """
    Train Linear, Ridge, Lasso. Save each to disk.
    Returns list of result dicts for the caller to persist.
    """
    X_real, y_real = _get_real_training_data()
    if X_real is not None:
        X, y = X_real, y_real
        source = 'real'
    else:
        X, y = _generate_training_data()
        source = 'synthetic'

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42)

    estimators = {
        'linear': LinearRegression(),
        'ridge':  Ridge(alpha=1.0),
        'lasso':  Lasso(alpha=0.1, max_iter=5000),
    }

    results = []
    for name, est in estimators.items():
        pipe = Pipeline([('scaler', StandardScaler()), ('model', est)])
        pipe.fit(X_train, y_train)
        y_pred = pipe.predict(X_test)

        r2   = float(r2_score(y_test, y_pred))
        mae  = float(mean_absolute_error(y_test, y_pred))
        rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))

        path = MODELS_DIR / f'yield_{name}.pkl'
        joblib.dump(pipe, path)

        results.append({
            'model_type':       name,
            'r2_score':         round(r2,   4),
            'mae':              round(mae,  4),
            'rmse':             round(rmse, 4),
            'training_samples': len(X_train),
            'model_file':       str(path),
            'notes':            f'Trained on {source} data ({len(X)} samples)',
        })

    # Mark the best model (highest R²) as active
    best = max(results, key=lambda r: r['r2_score'])
    for r in results:
        r['is_active'] = (r['model_type'] == best['model_type'])

    return results


def predict_yield(features: dict) -> dict:
    """
    Run prediction using the active (best) model.
    Returns predicted yield + which model was used.
    """
    from apps.predictions.models import YieldPredictionModel

    active = YieldPredictionModel.objects.filter(is_active=True).first()
    if not active or not os.path.exists(active.model_file):
        # Fall back to a simple heuristic if no model trained yet
        base = float(features.get('variety_avg_yield', 5.0))
        return {'predicted_yield_t_ha': round(base * 0.85, 2),
                'model_used': 'heuristic', 'r2_score': None}

    pipe = joblib.load(active.model_file)
    X    = encode_features(features)
    pred = float(pipe.predict(X)[0])
    pred = max(1.0, min(pred, 12.0))

    return {
        'predicted_yield_t_ha': round(pred, 2),
        'model_used':           active.get_model_type_display(),
        'r2_score':             active.r2_score,
    }
