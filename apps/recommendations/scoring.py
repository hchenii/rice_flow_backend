"""
RSI Weighted Scoring Engine.

Reads FAO suitability ranges and WLC weights from the database
(SuitabilityRuleSet) when present, and falls back to the hardcoded
DEFAULT_PAYLOAD below if the database row is missing or unreadable.
This guarantees the recommendation engine keeps working even if the
admin-configurable rules are unavailable.
"""

S1, S2, S3, N = 100, 75, 50, 25


# ──────────────────────────────────────────────────────────────────────────
# Hardcoded fallback — mirrors the values seeded in
# migrations/0003_seed_default_rules.py and the original constants
# of this file before the admin-editable layer was added.
# ──────────────────────────────────────────────────────────────────────────
DEFAULT_PAYLOAD = {
    'rules': [
        {'key': 'soil_ph',           'weight': 0.08, 'type': 'range',
         's1': {'min': 5.5, 'max': 6.5},
         's2': {'min': 5.0, 'max': 7.0},
         's3': {'min': 4.5, 'max': 8.0}},

        {'key': 'soil_texture',      'weight': 0.10, 'type': 'categorical',
         'options': [
             {'value': 'clay',             'score': 'S1'},
             {'value': 'clay loam',        'score': 'S1'},
             {'value': 'silty clay',       'score': 'S1'},
             {'value': 'silt loam',        'score': 'S2'},
             {'value': 'silty clay loam',  'score': 'S2'},
             {'value': 'sandy loam',       'score': 'S3'},
             {'value': 'sandy clay loam',  'score': 'S3'},
         ]},

        {'key': 'organic_matter',    'weight': 0.05, 'type': 'threshold',
         's1': 3.0, 's2': 2.0, 's3': 1.0},

        {'key': 'drainage',          'weight': 0.07, 'type': 'ecosystem_categorical',
         'perEcosystem': {
             'irrigated_lowland': [
                 {'value': 'poorly drained',     'score': 'S1'},
                 {'value': 'moderately drained', 'score': 'S2'},
                 {'value': 'well drained',       'score': 'S3'},
             ],
             'rainfed_lowland': [
                 {'value': 'poorly drained',     'score': 'S1'},
                 {'value': 'moderately drained', 'score': 'S2'},
                 {'value': 'well drained',       'score': 'S3'},
             ],
             'upland': [
                 {'value': 'well drained',       'score': 'S1'},
                 {'value': 'moderately drained', 'score': 'S2'},
                 {'value': 'poorly drained',     'score': 'S3'},
             ],
         }},

        {'key': 'avg_temperature',   'weight': 0.12, 'type': 'range',
         's1': {'min': 24, 'max': 30},
         's2': {'min': 22, 'max': 33},
         's3': {'min': 20, 'max': 35}},

        {'key': 'seasonal_rainfall', 'weight': 0.15, 'type': 'threshold',
         's1': 1000, 's2': 700, 's3': 500},

        {'key': 'humidity',          'weight': 0.04, 'type': 'range',
         's1': {'min': 70, 'max': 90},
         's2': {'min': 60, 'max': 95},
         's3': {'min': 50, 'max': 100}},

        {'key': 'solar_radiation',   'weight': 0.06, 'type': 'threshold',
         's1': 18, 's2': 15, 's3': 12},

        {'key': 'temp_at_flowering', 'weight': 0.08, 'type': 'range',
         's1': {'min': 25, 'max': 30},
         's2': {'min': 22, 'max': 33},
         's3': {'min': 20, 'max': 35}},

        {'key': 'elevation',         'weight': 0.08, 'type': 'ecosystem_threshold',
         'perEcosystem': {
             'irrigated_lowland': {'s1': 300,  's2': 600,  's3': 1000},
             'rainfed_lowland':   {'s1': 500,  's2': 800,  's3': 1000},
             'upland':            {'s1': 1000, 's2': 1500, 's3': 2000},
         }},

        {'key': 'slope',             'weight': 0.07, 'type': 'ecosystem_threshold',
         'perEcosystem': {
             'irrigated_lowland': {'s1': 2,  's2': 5,  's3': 8 },
             'rainfed_lowland':   {'s1': 3,  's2': 8,  's3': 15},
             'upland':            {'s1': 15, 's2': 25, 's3': 35},
         }},

        {'key': 'stress_tolerance',  'weight': 0.10, 'type': 'derived'},
    ],
}


def default_rules_payload():
    """Public helper so views.py can return the fallback shape."""
    return DEFAULT_PAYLOAD


# ──────────────────────────────────────────────────────────────────────────
# Rule loader with safe fallback
# ──────────────────────────────────────────────────────────────────────────
def _load_rules_by_key():
    """
    Try to fetch the admin-edited rules. If anything goes wrong
    (DB unavailable, row missing, malformed payload) we silently
    fall back to DEFAULT_PAYLOAD so the recommendation engine
    keeps working.
    """
    payload = DEFAULT_PAYLOAD
    try:
        from .models import SuitabilityRuleSet
        rs = SuitabilityRuleSet.objects.first()
        if rs and isinstance(rs.payload, dict) and rs.payload.get('rules'):
            payload = rs.payload
    except Exception:
        payload = DEFAULT_PAYLOAD

    by_key = {}
    for r in payload.get('rules', []):
        if isinstance(r, dict) and 'key' in r:
            by_key[r['key']] = r

    # Fill gaps with defaults so a partial DB payload can't break anything.
    for r in DEFAULT_PAYLOAD['rules']:
        by_key.setdefault(r['key'], r)
    return by_key


def _weights(rules_by_key):
    return {k: float(r.get('weight', 0) or 0) for k, r in rules_by_key.items()}


# ──────────────────────────────────────────────────────────────────────────
# Per-factor scoring (each receives its rule dict)
# ──────────────────────────────────────────────────────────────────────────
def _score_range(value, rule):
    try:
        s1, s2, s3 = rule['s1'], rule['s2'], rule['s3']
        if s1['min'] <= value <= s1['max']: return S1
        if s2['min'] <= value <= s2['max']: return S2
        if s3['min'] <= value <= s3['max']: return S3
    except Exception:
        pass
    return N


def _score_threshold(value, rule):
    try:
        if value >= rule['s1']: return S1
        if value >= rule['s2']: return S2
        if value >= rule['s3']: return S3
    except Exception:
        pass
    return N


def _score_categorical(value, rule):
    if not value:
        return N
    v = str(value).lower().strip()
    options = rule.get('options', [])
    # Match most-specific first so 'silty clay loam' isn't caught by 'clay'.
    score_map = {S1: 'S1', S2: 'S2', S3: 'S3'}
    for length_pref in sorted({len(o['value']) for o in options}, reverse=True):
        for o in options:
            if len(o['value']) == length_pref and o['value'].lower() in v:
                cls = o.get('score', 'N')
                if cls == 'S1': return S1
                if cls == 'S2': return S2
                if cls == 'S3': return S3
    return N


def _score_eco_categorical(value, ecosystem, rule):
    per = rule.get('perEcosystem', {})
    sub_rule = {'options': per.get(ecosystem, [])}
    return _score_categorical(value, sub_rule)


def _score_eco_threshold(value, ecosystem, rule):
    per = rule.get('perEcosystem', {}).get(ecosystem)
    if not per:
        return N
    try:
        if value <= per['s1']: return S1
        if value <= per['s2']: return S2
        if value <= per['s3']: return S3
    except Exception:
        pass
    return N


def _score_stress_tolerance(variety, scan, rule=None):
    """
    Derived score: combines variety tolerances with environmental risk
    levels reported in the scan. Hardcoded logic (not configurable).
    """
    flood_risk    = (scan.flood_risk or 'Low').lower() if hasattr(scan, 'flood_risk') else 'low'
    drought_risk  = 'low'
    salinity_risk = 'low'

    score = S1
    sub_tol = getattr(variety, 'submergence_tolerance', 'moderate') or 'moderate'
    dro_tol = getattr(variety, 'drought_tolerance', 'moderate')     or 'moderate'
    sal_tol = getattr(variety, 'salinity_tolerance', 'moderate')    or 'moderate'

    if flood_risk == 'high' and sub_tol == 'low':
        score = N
    elif flood_risk == 'moderate' and sub_tol == 'low':
        score = min(score, S2)
    if drought_risk == 'high' and dro_tol == 'low':
        score = min(score, S2)
    if salinity_risk == 'high' and sal_tol == 'low':
        score = min(score, S2)
    return score


# ──────────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────────
def calculate_rsi(variety, scan, ecosystem: str) -> dict:
    rules   = _load_rules_by_key()
    weights = _weights(rules)

    scores = {
        'soil_ph':           _score_range       (scan.soil_ph                  or 6.2,  rules['soil_ph']),
        'soil_texture':      _score_categorical (scan.soil_texture             or 'clay loam', rules['soil_texture']),
        'organic_matter':    _score_threshold   (scan.organic_matter           or 2.5,  rules['organic_matter']),
        'drainage':          _score_eco_categorical(scan.drainage              or 'poorly drained', ecosystem, rules['drainage']),
        'avg_temperature':   _score_range       (scan.avg_temperature          or 27,   rules['avg_temperature']),
        'seasonal_rainfall': _score_threshold   (scan.seasonal_rainfall_mm     or 1200, rules['seasonal_rainfall']),
        'humidity':          _score_range       (scan.humidity_pct             or 82,   rules['humidity']),
        'solar_radiation':   _score_threshold   (scan.solar_radiation          or 17,   rules['solar_radiation']),
        'temp_at_flowering': _score_range       (scan.temp_at_flowering        or 27,   rules['temp_at_flowering']),
        'elevation':         _score_eco_threshold(scan.elevation_m             or 45,   ecosystem, rules['elevation']),
        'slope':             _score_eco_threshold(scan.slope_pct               or 1,    ecosystem, rules['slope']),
        'stress_tolerance':  _score_stress_tolerance(variety, scan, rules.get('stress_tolerance')),
    }

    rsi = round(sum(scores[k] * weights.get(k, 0) for k in scores), 2)
    suitability_class = (
        'S1 - Highly Suitable'        if rsi >= 85 else
        'S2 - Moderately Suitable'    if rsi >= 70 else
        'S3 - Marginally Suitable'    if rsi >= 50 else
        'N1 - Currently Not Suitable' if rsi >= 30 else
        'N2 - Not Suitable'
    )

    return {
        'rsi_score':        rsi,
        'suitability_class': suitability_class,
        'factor_scores':    scores,
    }
