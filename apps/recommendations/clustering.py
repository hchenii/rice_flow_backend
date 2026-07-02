"""
Clustering Engine — K-Means.

Groups rice varieties by agro-climatic similarity. Each variety becomes a
9-feature vector; features are standardized; K-Means assigns a cluster label
that is stored as supplementary metadata on recommendation results (the
ranking itself is purely RSI).

Training searches k = 2..8 and keeps the k with the best silhouette score,
using n_init=50 and a fixed random_state so results are stable and
reproducible across runs.
"""
import time
import numpy as np
import joblib
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score, davies_bouldin_score
from django.conf import settings

MODELS_DIR = settings.MODELS_DIR

TOLERANCE_MAP = {'low': 0, 'moderate': 1, 'high': 2}
ECOSYSTEM_MAP = {'irrigated_lowland': 0, 'rainfed_lowland': 1, 'upland': 2}

# Search range for the number of clusters (upper bound also capped at n-1)
K_MIN = 2
K_MAX = 8


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


def train_all_models(varieties, n_clusters=None):
    """
    Train K-Means on the variety feature matrix.

    Searches k in [K_MIN, min(K_MAX, n-1)] and keeps the k with the highest
    silhouette score — unless `n_clusters` pins a specific k. Persists the
    fitted scaler + model to disk.

    Returns ({'kmeans': metrics}, X_scaled). The metrics dict includes a
    `search_log` listing silhouette/DBI for every k tried, for transparency.
    """
    X = _build_feature_matrix(varieties)
    n_samples = X.shape[0]
    if n_samples < K_MIN + 1:
        raise ValueError(f'Need at least {K_MIN + 1} varieties to cluster (got {n_samples}).')

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    k_hi = min(K_MAX, n_samples - 1)
    candidates = [int(n_clusters)] if n_clusters else list(range(K_MIN, k_hi + 1))

    best, search_log = None, []
    t0 = time.perf_counter()
    for k in candidates:
        km = KMeans(n_clusters=k, random_state=42, n_init=50)
        labels = km.fit_predict(X_scaled)
        sil = round(float(silhouette_score(X_scaled, labels)), 4)
        dbi = round(float(davies_bouldin_score(X_scaled, labels)), 4)
        search_log.append({'k': k, 'silhouette': sil, 'davies_bouldin': dbi})
        if best is None or sil > best['silhouette']:
            best = {
                'model':          km,
                'labels':         labels.tolist(),
                'silhouette':     sil,
                'davies_bouldin': dbi,
                'n_clusters':     k,
            }
    best['training_time_ms'] = round((time.perf_counter() - t0) * 1000, 3)
    best['search_log']       = search_log

    joblib.dump(scaler, MODELS_DIR / 'scaler.pkl')
    joblib.dump(best['model'], MODELS_DIR / 'kmeans.pkl')

    return {'kmeans': best}, X_scaled


def predict_cluster(variety, active_model_name: str = 'kmeans') -> int:
    """Cluster label for a single variety (0 if the model isn't trained yet)."""
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


def get_farm_cluster(scan, ecosystem: str, active_model_name: str = 'kmeans') -> int:
    """Cluster label for a farm, derived from its latest environmental scan."""
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
