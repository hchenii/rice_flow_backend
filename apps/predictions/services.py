"""
Yield prediction service — Linear Regression.

The model predicts yield (t/ha) from 11 raw farm/variety features plus
engineered agronomic features. Linear Regression can only learn straight-line
relationships, so the non-linear agronomy (pH sweet spot, heat stress,
drought/waterlogging) is captured by explicitly engineered feature columns —
computed identically at train and predict time.

Validation: 5-fold cross-validation on the training split (reported in notes)
plus held-out test metrics R², MAE, RMSE (the saved headline numbers).

Training data: real YieldRecord rows once >= 30 exist; until then a synthetic
dataset whose relationships follow documented rice agronomy (pH optimum around
6.2, stress above 33 °C, drought below ~1400 mm, waterlogging above ~2600 mm).
"""
import os
import numpy as np
import joblib
from pathlib import Path
from django.conf import settings

from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error

MODELS_DIR: Path = settings.MODELS_DIR

RAW_FEATURES = [
    'area_ha', 'soil_ph', 'organic_matter', 'avg_temperature',
    'seasonal_rainfall', 'humidity', 'elevation_m',
    'flood_risk_enc',   # low=0, moderate=1, high=2
    'ecosystem_enc',    # lowland=0, upland=1
    'maturity_days', 'variety_avg_yield',
]
ENGINEERED_FEATURES = [
    'ph_stress',      # squared distance from the pH 6.2 optimum
    'heat_stress',    # degrees above 33 °C (0 below)
    'rain_deficit',   # 1000-mm units below 1400 mm (drought)
    'rain_excess',    # 1000-mm units above 2600 mm (waterlogging)
    'flood_x_rain',   # flood-prone farms suffer more from excess rain
    'ph_x_om',        # pH × organic matter interaction (nutrient availability)
]
FEATURE_NAMES = RAW_FEATURES + ENGINEERED_FEATURES

FLOOD_MAP = {'low': 0, 'moderate': 1, 'high': 2}
ECO_MAP   = {'lowland': 0, 'irrigated_lowland': 0, 'rainfed_lowland': 0,
             'upland': 1, 'highland': 1}

PH_OPTIMUM     = 6.2
HEAT_THRESHOLD = 33.0    # °C — spikelet sterility risk above this at flowering
RAIN_LOW       = 1400.0  # mm — below this the crop is water-limited
RAIN_HIGH      = 2600.0  # mm — above this waterlogging/flood losses grow


def encode_features(raw: dict) -> np.ndarray:
    """Map a request payload to the 11 raw feature columns (1 row)."""
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


def engineer_features(X_raw: np.ndarray) -> np.ndarray:
    """
    Append the engineered agronomic columns to a (n × 11) raw matrix.
    Must stay identical between training and prediction.
    """
    ph        = X_raw[:, 1]
    om        = X_raw[:, 2]
    temp      = X_raw[:, 3]
    rain      = X_raw[:, 4]
    flood_enc = X_raw[:, 7]

    ph_stress    = (ph - PH_OPTIMUM) ** 2
    heat_stress  = np.maximum(0.0, temp - HEAT_THRESHOLD)
    rain_deficit = np.maximum(0.0, RAIN_LOW - rain) / 1000.0
    rain_excess  = np.maximum(0.0, rain - RAIN_HIGH) / 1000.0
    flood_x_rain = flood_enc * rain_excess
    ph_x_om      = ph * om

    return np.column_stack([
        X_raw, ph_stress, heat_stress, rain_deficit, rain_excess,
        flood_x_rain, ph_x_om,
    ])


def _generate_training_data(n_samples: int = 5000) -> tuple:
    """
    Synthetic dataset following documented rice-agronomy relationships.
    Used until enough real YieldRecords accumulate. Ranges are wide enough
    (drought through waterlogging, mild through hot) that the model learns
    the stress responses, not just the comfortable middle.
    """
    rng = np.random.default_rng(42)

    area_ha        = rng.uniform(0.5, 5.0,   n_samples)
    soil_ph        = rng.uniform(4.5, 8.0,   n_samples)
    organic_matter = rng.uniform(0.5, 4.0,   n_samples)
    avg_temp       = rng.uniform(24, 36,     n_samples)
    rainfall       = rng.uniform(800, 3500,  n_samples)
    humidity       = rng.uniform(60, 90,     n_samples)
    elevation_m    = rng.uniform(0, 600,     n_samples)
    flood_risk_enc = rng.integers(0, 3,      n_samples).astype(float)
    ecosystem_enc  = rng.integers(0, 2,      n_samples).astype(float)
    maturity_days  = rng.uniform(100, 130,   n_samples)
    variety_avg_y  = rng.uniform(4.0, 7.5,   n_samples)

    ph_stress    = (soil_ph - PH_OPTIMUM) ** 2
    heat_stress  = np.maximum(0.0, avg_temp - HEAT_THRESHOLD)
    rain_deficit = np.maximum(0.0, RAIN_LOW - rainfall) / 1000.0
    rain_excess  = np.maximum(0.0, rainfall - RAIN_HIGH) / 1000.0

    yield_t_ha = (
        variety_avg_y * 0.55                          # varietal potential
        + 1.2 * np.exp(-ph_stress / 0.9)              # pH sweet spot peaks at 6.2
        + 0.22 * organic_matter                       # fertility
        - 1.5 * rain_deficit                          # drought loss
        - 0.5 * rain_excess                           # waterlogging loss
        - 0.35 * flood_risk_enc * rain_excess         # worse on flood-prone land
        - 0.10 * heat_stress ** 1.5                   # non-linear heat sterility
        + 0.20 * (1 - ecosystem_enc)                  # lowland advantage
        - 0.15 * flood_risk_enc                       # baseline flood exposure
        - elevation_m / 2500.0                        # cooler/steeper marginal loss
        + rng.normal(0, 0.35, n_samples)              # field noise
    )
    yield_t_ha = np.clip(yield_t_ha, 1.5, 9.5)

    X = np.column_stack([
        area_ha, soil_ph, organic_matter, avg_temp,
        rainfall, humidity, elevation_m,
        flood_risk_enc, ecosystem_enc,
        maturity_days, variety_avg_y,
    ])
    return X, yield_t_ha


def _get_real_training_data():
    """Pull actual YieldRecord rows if there are enough of them."""
    from apps.progress.models import YieldRecord
    from apps.environmental.models import EnvironmentalScan

    rows = (YieldRecord.objects
            .select_related('farm_cycle__farm', 'farm_cycle__variety')
            .filter(net_yield_kg__gt=0))

    X_rows, y_rows = [], []
    for yr in rows:
        cycle = yr.farm_cycle
        farm  = cycle.farm
        scan  = EnvironmentalScan.objects.filter(farm=farm).order_by('-id').first()
        if not scan:
            continue
        area = float(farm.area_ha or 1.0) if hasattr(farm, 'area_ha') else float(getattr(farm, 'area_hectares', 1.0) or 1.0)
        y_t_ha = (yr.net_yield_kg / 1000) / max(area, 0.1)
        X_rows.append([
            area,
            float(scan.soil_ph),
            float(scan.organic_matter),
            float(scan.avg_temperature),
            float(getattr(scan, 'seasonal_rainfall_mm', None) or getattr(scan, 'seasonal_rainfall', 0) or 0),
            float(getattr(scan, 'humidity_pct', None) or getattr(scan, 'humidity', 0) or 0),
            float(scan.elevation_m),
            FLOOD_MAP.get(str(scan.flood_risk or 'low').lower(), 0),
            ECO_MAP.get(str(farm.ecosystem or 'lowland').lower(), 0),
            float(cycle.variety.maturity_days),
            float(cycle.variety.avg_yield_t_ha),
        ])
        y_rows.append(y_t_ha)

    if len(X_rows) < 30:
        return None, None
    return np.array(X_rows), np.array(y_rows)


def train_all_models():
    """
    Train the Linear Regression yield model.

    Returns a single-item list (kept as a list so callers that iterate results
    keep working) with the test metrics; 5-fold CV results go into notes.
    """
    X_real, y_real = _get_real_training_data()
    if X_real is not None:
        X_raw, y = X_real, y_real
        source = 'real'
    else:
        X_raw, y = _generate_training_data()
        source = 'synthetic'

    X = engineer_features(X_raw)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42)

    pipe = Pipeline([('scaler', StandardScaler()), ('model', LinearRegression())])

    # 5-fold CV on the training split → a stability estimate, not one lucky split
    cv_scores = cross_val_score(pipe, X_train, y_train, cv=5, scoring='r2')
    cv_mean, cv_std = float(cv_scores.mean()), float(cv_scores.std())

    pipe.fit(X_train, y_train)
    y_pred = pipe.predict(X_test)

    r2   = float(r2_score(y_test, y_pred))
    mae  = float(mean_absolute_error(y_test, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))

    path = MODELS_DIR / 'yield_linear.pkl'
    joblib.dump(pipe, path)

    return [{
        'model_type':       'linear',
        'r2_score':         round(r2,   4),
        'mae':              round(mae,  4),
        'rmse':             round(rmse, 4),
        'training_samples': len(X_train),
        'model_file':       str(path),
        'is_active':        True,
        'notes':            (
            f'Trained on {source} data ({len(X)} samples, '
            f'{len(FEATURE_NAMES)} features incl. engineered agronomy). '
            f'5-fold CV R2 = {cv_mean:.4f} ± {cv_std:.4f}.'
        ),
    }]


def predict_yield(features: dict) -> dict:
    """
    Run prediction using the active model. Returns predicted yield + which
    model produced it. Falls back to a simple heuristic if nothing is trained.
    """
    from apps.predictions.models import YieldPredictionModel

    active = YieldPredictionModel.objects.filter(is_active=True).first()
    if not active or not os.path.exists(active.model_file):
        base = float(features.get('variety_avg_yield', 5.0))
        return {'predicted_yield_t_ha': round(base * 0.85, 2),
                'model_used': 'heuristic', 'r2_score': None}

    pipe = joblib.load(active.model_file)
    X    = engineer_features(encode_features(features))
    pred = float(pipe.predict(X)[0])
    pred = max(1.0, min(pred, 12.0))

    return {
        'predicted_yield_t_ha': round(pred, 2),
        'model_used':           active.get_model_type_display(),
        'r2_score':             active.r2_score,
    }
