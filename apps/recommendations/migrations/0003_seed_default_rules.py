"""
Seed the SuitabilityRuleSet singleton with values that exactly mirror the
hardcoded constants in apps/recommendations/scoring.py at the time of
this migration. If the seed is later changed through the admin, those
edits override the seed values.
"""
from django.db import migrations


DEFAULT_PAYLOAD = {
    'rules': [
        # ── SOIL ────────────────────────────────────────────────────────
        {
            'key': 'soil_ph',           'label': 'Soil pH',
            'group': 'Soil',            'unit': 'pH',
            'weight': 0.08,             'type': 'range',
            's1': {'min': 5.5, 'max': 6.5},
            's2': {'min': 5.0, 'max': 7.0},
            's3': {'min': 4.5, 'max': 8.0},
        },
        {
            'key': 'soil_texture',      'label': 'Soil Texture',
            'group': 'Soil',            'unit': 'texture class',
            'weight': 0.10,             'type': 'categorical',
            'options': [
                {'value': 'clay',             'score': 'S1'},
                {'value': 'clay loam',        'score': 'S1'},
                {'value': 'silty clay',       'score': 'S1'},
                {'value': 'silt loam',        'score': 'S2'},
                {'value': 'silty clay loam',  'score': 'S2'},
                {'value': 'sandy loam',       'score': 'S3'},
                {'value': 'sandy clay loam',  'score': 'S3'},
            ],
        },
        {
            'key': 'organic_matter',    'label': 'Organic Matter',
            'group': 'Soil',            'unit': '%',
            'weight': 0.05,             'type': 'threshold',
            's1': 3.0, 's2': 2.0, 's3': 1.0,
        },
        {
            'key': 'drainage',          'label': 'Drainage',
            'group': 'Soil',            'unit': 'drainage class',
            'weight': 0.07,             'type': 'ecosystem_categorical',
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
            },
        },

        # ── CLIMATE ─────────────────────────────────────────────────────
        {
            'key': 'avg_temperature',   'label': 'Average Temperature',
            'group': 'Climate',         'unit': '°C',
            'weight': 0.12,             'type': 'range',
            's1': {'min': 24, 'max': 30},
            's2': {'min': 22, 'max': 33},
            's3': {'min': 20, 'max': 35},
        },
        {
            'key': 'seasonal_rainfall', 'label': 'Seasonal Rainfall',
            'group': 'Climate',         'unit': 'mm',
            'weight': 0.15,             'type': 'threshold',
            's1': 1000, 's2': 700, 's3': 500,
        },
        {
            'key': 'humidity',          'label': 'Relative Humidity',
            'group': 'Climate',         'unit': '%',
            'weight': 0.04,             'type': 'range',
            's1': {'min': 70, 'max': 90},
            's2': {'min': 60, 'max': 95},
            's3': {'min': 50, 'max': 100},
        },
        {
            'key': 'solar_radiation',   'label': 'Solar Radiation',
            'group': 'Climate',         'unit': 'MJ/m²/day',
            'weight': 0.06,             'type': 'threshold',
            's1': 18, 's2': 15, 's3': 12,
        },
        {
            'key': 'temp_at_flowering', 'label': 'Temperature at Flowering',
            'group': 'Climate',         'unit': '°C',
            'weight': 0.08,             'type': 'range',
            's1': {'min': 25, 'max': 30},
            's2': {'min': 22, 'max': 33},
            's3': {'min': 20, 'max': 35},
        },

        # ── TOPOGRAPHY ──────────────────────────────────────────────────
        {
            'key': 'elevation',         'label': 'Elevation',
            'group': 'Topography',      'unit': 'm',
            'weight': 0.08,             'type': 'ecosystem_threshold',
            'perEcosystem': {
                'irrigated_lowland': {'s1': 300,  's2': 600,  's3': 1000},
                'rainfed_lowland':   {'s1': 500,  's2': 800,  's3': 1000},
                'upland':            {'s1': 1000, 's2': 1500, 's3': 2000},
            },
        },
        {
            'key': 'slope',             'label': 'Slope',
            'group': 'Topography',      'unit': '%',
            'weight': 0.07,             'type': 'ecosystem_threshold',
            'perEcosystem': {
                'irrigated_lowland': {'s1': 2,  's2': 5,  's3': 8 },
                'rainfed_lowland':   {'s1': 3,  's2': 8,  's3': 15},
                'upland':            {'s1': 15, 's2': 25, 's3': 35},
            },
        },

        # ── VARIETY STRESS (derived) ────────────────────────────────────
        {
            'key': 'stress_tolerance',  'label': 'Stress Tolerance',
            'group': 'Variety',         'unit': 'derived',
            'weight': 0.10,             'type': 'derived',
            'description': (
                "Combines flood, drought, and salinity risk with the variety's "
                "tolerance profile. Cannot be edited directly — modify variety "
                "tolerances on the Datasets page instead."
            ),
        },
    ],
}


def seed_rules(apps, schema_editor):
    SuitabilityRuleSet = apps.get_model('recommendations', 'SuitabilityRuleSet')
    SuitabilityRuleSet.objects.update_or_create(
        pk=1, defaults={'payload': DEFAULT_PAYLOAD}
    )


def unseed_rules(apps, schema_editor):
    SuitabilityRuleSet = apps.get_model('recommendations', 'SuitabilityRuleSet')
    SuitabilityRuleSet.objects.filter(pk=1).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('recommendations', '0002_add_suitability_rules'),
    ]
    operations = [
        migrations.RunPython(seed_rules, unseed_rules),
    ]
