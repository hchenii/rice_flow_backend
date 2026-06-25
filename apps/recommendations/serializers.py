from rest_framework import serializers
from .models import ClusterModel, Recommendation, RecommendationResult, SuitabilityRuleSet
from apps.varieties.models import RiceVariety


VALID_CLASS_SCORES = {'S1', 'S2', 'S3'}
VALID_ECOSYSTEMS   = {'irrigated_lowland', 'rainfed_lowland', 'upland'}


def _label(rule):
    return rule.get('label') or rule.get('key') or '(unknown factor)'


def _validate_range_rule(rule):
    """For 'range' type: each class needs min<=max, and S1 must nest inside S2 inside S3."""
    errors = []
    label  = _label(rule)
    bounds = {}
    for cls in ('s1', 's2', 's3'):
        band = rule.get(cls)
        if not isinstance(band, dict) or 'min' not in band or 'max' not in band:
            errors.append(f"{label}: missing {cls.upper()} min/max.")
            continue
        try:
            lo, hi = float(band['min']), float(band['max'])
        except (TypeError, ValueError):
            errors.append(f"{label}: {cls.upper()} min/max must be numbers.")
            continue
        if lo > hi:
            errors.append(f"{label}: {cls.upper()} min ({lo}) must be <= max ({hi}).")
        bounds[cls] = (lo, hi)

    # S1 must be inside S2, S2 inside S3 (outer-envelope FAO representation).
    if 's1' in bounds and 's2' in bounds:
        s1_lo, s1_hi = bounds['s1']
        s2_lo, s2_hi = bounds['s2']
        if s2_lo > s1_lo or s2_hi < s1_hi:
            errors.append(f"{label}: S2 range must fully contain S1.")
    if 's2' in bounds and 's3' in bounds:
        s2_lo, s2_hi = bounds['s2']
        s3_lo, s3_hi = bounds['s3']
        if s3_lo > s2_lo or s3_hi < s2_hi:
            errors.append(f"{label}: S3 range must fully contain S2.")
    return errors


def _validate_threshold_rule(rule):
    """For 'threshold' type: higher = better, so S1 > S2 > S3."""
    errors = []
    label  = _label(rule)
    vals = {}
    for cls in ('s1', 's2', 's3'):
        try:
            vals[cls] = float(rule.get(cls))
        except (TypeError, ValueError):
            errors.append(f"{label}: {cls.upper()} threshold must be a number.")
    if {'s1', 's2'}.issubset(vals) and vals['s1'] < vals['s2']:
        errors.append(f"{label}: S1 threshold ({vals['s1']}) must be >= S2 ({vals['s2']}).")
    if {'s2', 's3'}.issubset(vals) and vals['s2'] < vals['s3']:
        errors.append(f"{label}: S2 threshold ({vals['s2']}) must be >= S3 ({vals['s3']}).")
    return errors


def _validate_ecosystem_threshold_rule(rule):
    """For 'ecosystem_threshold' (elevation, slope): lower = better, S1 < S2 < S3 per ecosystem."""
    errors = []
    label  = _label(rule)
    per = rule.get('perEcosystem') or {}
    if not isinstance(per, dict):
        return [f"{label}: perEcosystem must be an object."]
    for eco in VALID_ECOSYSTEMS:
        eco_rule = per.get(eco)
        if not isinstance(eco_rule, dict):
            errors.append(f"{label}: missing thresholds for {eco}.")
            continue
        vals = {}
        for cls in ('s1', 's2', 's3'):
            try:
                vals[cls] = float(eco_rule.get(cls))
            except (TypeError, ValueError):
                errors.append(f"{label} ({eco}): {cls.upper()} threshold must be a number.")
        if {'s1', 's2'}.issubset(vals) and vals['s1'] > vals['s2']:
            errors.append(f"{label} ({eco}): S1 ({vals['s1']}) must be <= S2 ({vals['s2']}).")
        if {'s2', 's3'}.issubset(vals) and vals['s2'] > vals['s3']:
            errors.append(f"{label} ({eco}): S2 ({vals['s2']}) must be <= S3 ({vals['s3']}).")
    return errors


def _validate_categorical_options(label, options, ctx=''):
    errors = []
    if not isinstance(options, list) or len(options) == 0:
        errors.append(f"{label}{ctx}: options must be a non-empty list.")
        return errors
    for i, opt in enumerate(options):
        if not isinstance(opt, dict):
            errors.append(f"{label}{ctx}: option #{i + 1} must be an object.")
            continue
        v = opt.get('value')
        s = opt.get('score')
        if not isinstance(v, str) or not v.strip():
            errors.append(f"{label}{ctx}: option #{i + 1} value must be a non-empty string.")
        if s not in VALID_CLASS_SCORES:
            errors.append(f"{label}{ctx}: option #{i + 1} score must be one of S1/S2/S3.")
    return errors


def _validate_categorical_rule(rule):
    return _validate_categorical_options(_label(rule), rule.get('options', []))


def _validate_ecosystem_categorical_rule(rule):
    errors = []
    label  = _label(rule)
    per = rule.get('perEcosystem') or {}
    if not isinstance(per, dict):
        return [f"{label}: perEcosystem must be an object."]
    for eco in VALID_ECOSYSTEMS:
        if eco not in per:
            errors.append(f"{label}: missing options for {eco}.")
            continue
        errors.extend(_validate_categorical_options(label, per.get(eco, []), f" ({eco})"))
    return errors


VALIDATORS_BY_TYPE = {
    'range':                 _validate_range_rule,
    'threshold':             _validate_threshold_rule,
    'ecosystem_threshold':   _validate_ecosystem_threshold_rule,
    'categorical':           _validate_categorical_rule,
    'ecosystem_categorical': _validate_ecosystem_categorical_rule,
    'derived':               lambda r: [],  # nothing to validate
}


class SuitabilityRuleSetSerializer(serializers.ModelSerializer):
    updated_by_name = serializers.CharField(source='updated_by.email', read_only=True)

    class Meta:
        model  = SuitabilityRuleSet
        fields = ['payload', 'updated_at', 'updated_by_name']
        read_only_fields = ['updated_at', 'updated_by_name']

    def validate_payload(self, value):
        if not isinstance(value, dict) or 'rules' not in value:
            raise serializers.ValidationError(
                'Payload must be an object with a "rules" array.'
            )
        rules = value.get('rules', [])
        if not isinstance(rules, list) or len(rules) == 0:
            raise serializers.ValidationError('rules must be a non-empty array.')

        # Weights must sum to 1.00 and each must be 0..1.
        errors = []
        for r in rules:
            try:
                w = float(r.get('weight', 0) or 0)
            except (TypeError, ValueError):
                errors.append(f"{_label(r)}: weight must be a number.")
                continue
            if w < 0 or w > 1:
                errors.append(f"{_label(r)}: weight must be between 0 and 1 (got {w}).")
        total = sum(float(r.get('weight', 0) or 0) for r in rules)
        if abs(total - 1.0) > 0.005:
            errors.append(f"WLC weights must sum to 1.00 (got {total:.3f}).")

        # Per-rule structural sanity.
        for r in rules:
            rtype = r.get('type')
            validator = VALIDATORS_BY_TYPE.get(rtype)
            if validator is None:
                errors.append(f"{_label(r)}: unknown rule type '{rtype}'.")
                continue
            errors.extend(validator(r))

        if errors:
            raise serializers.ValidationError(errors)
        return value


class RiceVarietyBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RiceVariety
        fields = ['id', 'variety_id', 'nsic_code', 'common_name', 'ecosystem',
                  'avg_yield_t_ha', 'max_yield_t_ha', 'maturity_days',
                  'submergence_tolerance', 'drought_tolerance', 'salinity_tolerance', 'notes']


class RecommendationResultSerializer(serializers.ModelSerializer):
    variety = RiceVarietyBriefSerializer(read_only=True)

    class Meta:
        model  = RecommendationResult
        fields = ['rank', 'rsi_score', 'suitability_class', 'variety_cluster', 'factor_scores', 'variety']


class RecommendationSerializer(serializers.ModelSerializer):
    results = RecommendationResultSerializer(many=True, read_only=True)

    class Meta:
        model  = Recommendation
        fields = ['id', 'farm', 'scan', 'farm_cluster', 'created_at', 'results']


class ClusterModelSerializer(serializers.ModelSerializer):
    name_display = serializers.CharField(source='get_name_display', read_only=True)

    class Meta:
        model  = ClusterModel
        fields = ['id', 'name', 'name_display', 'training_time_ms',
                  'silhouette_score', 'davies_bouldin', 'n_clusters', 'is_active', 'trained_at']
