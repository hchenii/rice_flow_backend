"""
Clustering Engine — 3 models compared by speed + quality.
Admin trains all 3, picks the best, that model is used for recommendations.
"""
import time
import numpy as np
import joblib
from pathlib import Path
from sklearn.cluster import KMeans, AgglomerativeClustering, DBSCAN
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score, davies_bouldin_score
from django.conf import settings

MODELS_DIR = settings.MODELS_DIR

TOLERANCE_MAP = {'low': 0, 'moderate': 1, 'high': 2}
ECOSYSTEM_MAP = {'irrigated_lowland': 0, 'rainfed_lowland': 1, 'upland': 2}


def _build_feature_matrix(varieties):
    rows = []
    for v in varieties:
        rows.append([
            ECOSYSTEM_MAP.get(v.ecosystem, 0),
            TOLERANCE_MAP.get(v.submergence_tolerance, 0),
            TOLERANCE_MAP.get(v.drought_tolerance, 0),
            TOLERANCE_MAP.get(v.salinity_tolerance, 0),
            v.avg_yield_t_ha,
            v.maturity_days,
            v.optimal_temp_min,
            v.optimal_temp_max,
            v.optimal_rainfall_min / 1000,
        ])
    return np.array(rows, dtype=float)


def train_all_models(varieties, n_clusters=4):
    X = _build_feature_matrix(varieties)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    results = {}

    # ── 1. K-Means ─────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    km_labels = km.fit_predict(X_scaled)
    km_time = round((time.perf_counter() - t0) * 1000, 3)
    results['kmeans'] = {
        'model':           km,
        'labels':          km_labels.tolist(),
        'training_time_ms': km_time,
        'silhouette':      round(silhouette_score(X_scaled, km_labels), 4),
        'davies_bouldin':  round(davies_bouldin_score(X_scaled, km_labels), 4),
        'n_clusters':      n_clusters,
    }

    # ── 2. Agglomerative Hierarchical ──────────────────────────────────────
    t0 = time.perf_counter()
    ag = AgglomerativeClustering(n_clusters=n_clusters)
    ag_labels = ag.fit_predict(X_scaled)
    ag_time = round((time.perf_counter() - t0) * 1000, 3)
    results['agglomerative'] = {
        'model':           ag,
        'labels':          ag_labels.tolist(),
        'training_time_ms': ag_time,
        'silhouette':      round(silhouette_score(X_scaled, ag_labels), 4),
        'davies_bouldin':  round(davies_bouldin_score(X_scaled, ag_labels), 4),
        'n_clusters':      n_clusters,
    }

    # ── 3. DBSCAN ──────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    db = DBSCAN(eps=0.8, min_samples=2)
    db_labels = db.fit_predict(X_scaled)
    db_time = round((time.perf_counter() - t0) * 1000, 3)
    n_db_clusters = len(set(db_labels)) - (1 if -1 in db_labels else 0)
    try:
        db_sil = round(silhouette_score(X_scaled, db_labels), 4) if n_db_clusters > 1 else 0
        db_dbi = round(davies_bouldin_score(X_scaled, db_labels), 4) if n_db_clusters > 1 else 99
    except Exception:
        db_sil, db_dbi = 0, 99
    results['dbscan'] = {
        'model':           db,
        'labels':          db_labels.tolist(),
        'training_time_ms': db_time,
        'silhouette':      db_sil,
        'davies_bouldin':  db_dbi,
        'n_clusters':      n_db_clusters,
    }

    # Save scaler
    joblib.dump(scaler, MODELS_DIR / 'scaler.pkl')

    # Save each model
    for name, res in results.items():
        joblib.dump(res['model'], MODELS_DIR / f'{name}.pkl')

    return results, X_scaled


def predict_cluster(variety, active_model_name: str) -> int:
    scaler_path = MODELS_DIR / 'scaler.pkl'
    model_path  = MODELS_DIR / f'{active_model_name}.pkl'

    if not scaler_path.exists() or not model_path.exists():
        return 0

    scaler = joblib.load(scaler_path)
    model  = joblib.load(model_path)

    X = np.array([[
        ECOSYSTEM_MAP.get(variety.ecosystem, 0),
        TOLERANCE_MAP.get(variety.submergence_tolerance, 0),
        TOLERANCE_MAP.get(variety.drought_tolerance, 0),
        TOLERANCE_MAP.get(variety.salinity_tolerance, 0),
        variety.avg_yield_t_ha,
        variety.maturity_days,
        variety.optimal_temp_min,
        variety.optimal_temp_max,
        variety.optimal_rainfall_min / 1000,
    ]])
    X_scaled = scaler.transform(X)

    if hasattr(model, 'predict'):
        return int(model.predict(X_scaled)[0])
    return 0


def get_farm_cluster(scan, ecosystem: str, active_model_name: str) -> int:
    scaler_path = MODELS_DIR / 'scaler.pkl'
    model_path  = MODELS_DIR / f'{active_model_name}.pkl'

    if not scaler_path.exists() or not model_path.exists():
        return 0

    scaler = joblib.load(scaler_path)
    model  = joblib.load(model_path)

    X = np.array([[
        ECOSYSTEM_MAP.get(ecosystem, 0),
        1 if (scan.flood_risk or '').lower() == 'high' else 0,
        0,
        0,
        scan.avg_temperature or 27,
        scan.maturity_target if hasattr(scan, 'maturity_target') else 114,
        scan.avg_temperature or 22,
        (scan.avg_temperature or 27) + 8,
        (scan.annual_rainfall_mm or 2000) / 1000,
    ]])
    X_scaled = scaler.transform(X)

    if hasattr(model, 'predict'):
        return int(model.predict(X_scaled)[0])
    return 0
