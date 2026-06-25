"""
Management command: python manage.py load_seed_data
Loads all reference data: 17 rice varieties, 10 growth stages,
4 fertilizer applications, 13 pests/diseases.
Safe to re-run — uses get_or_create throughout.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.varieties.models import RiceVariety, GrowthStage, FertilizerSchedule, PestDisease


VARIETIES = [
    # variety_id, nsic_code, common_name, ecosystem, season, maturity_days, avg_yield, max_yield,
    # height_cm, grain_type, amylose_pct, subm_tol, drought_tol, salinity_tol,
    # pest_res, disease_res, temp_min, temp_max, rainfall_min, pagasa_types, year, notes
    ('V01', 'NSIC Rc222', 'NSIC Rc222 (Tubigan 18)',    'irrigated_lowland', 'Dry/Wet', 113, 5.2, 8.0,
     102, 'slender', 19.0, 'moderate', 'low', 'low',
     'BPH', 'BB, blast', 22, 35, 1200, 'I,II,III,IV', 2009,
     'Most widely planted variety in the Philippines'),

    ('V02', 'NSIC Rc160', 'NSIC Rc160 (Tubigan 7)',     'irrigated_lowland', 'Dry/Wet', 116, 5.1, 7.8,
     104, 'slender', 24.0, 'low', 'low', 'low',
     'BPH', 'BB', 22, 35, 1200, 'I,II,III,IV', 2005,
     'Popular in Mindanao irrigated areas'),

    ('V03', 'NSIC Rc238', 'NSIC Rc238 (Tubigan 21)',    'irrigated_lowland', 'Dry/Wet', 109, 5.4, 8.5,
     96, 'slender', 21.0, 'low', 'low', 'low',
     'BPH', 'BB, blast', 22, 35, 1200, 'I,II,III,IV', 2011,
     'Early maturing, high yielding'),

    ('V04', 'NSIC Rc216', 'NSIC Rc216 (Tubigan 15)',    'irrigated_lowland', 'Dry/Wet', 112, 5.0, 7.5,
     100, 'medium', 22.0, 'low', 'low', 'low',
     'GLH', 'BB', 22, 35, 1200, 'I,II,III,IV', 2008,
     'Good cooking quality'),

    ('V05', 'NSIC Rc9',   'NSIC Rc9 (Apo)',            'upland',            'Dry',     120, 3.5, 5.5,
     110, 'medium', 26.0, 'low', 'high', 'low',
     'BPH', 'blast', 18, 32, 1000, 'III,IV', 1995,
     'Classic upland variety, drought tolerant'),

    ('V06', 'NSIC Rc192', 'NSIC Rc192 (Sahod Ulan 1)', 'rainfed_lowland',   'Wet',     120, 3.8, 6.0,
     108, 'slender', 24.0, 'high', 'moderate', 'low',
     'BPH', 'BB', 22, 34, 1400, 'II,III,IV', 2007,
     'Submergence tolerant (Sub1 gene) — tolerates flash floods 12–14 days'),

    ('V07', 'NSIC Rc194', 'NSIC Rc194 (Sahod Ulan 2)', 'rainfed_lowland',   'Wet',     118, 4.0, 6.2,
     105, 'slender', 23.0, 'high', 'moderate', 'low',
     'GLH', 'BB', 22, 34, 1400, 'II,III,IV', 2007,
     'Sub1 variety with higher yield than Rc192'),

    ('V08', 'NSIC Rc272', 'NSIC Rc272 (Tubigan 25)',    'irrigated_lowland', 'Dry/Wet', 105, 5.6, 8.8,
     94, 'slender', 20.0, 'low', 'low', 'low',
     'BPH', 'BB, blast', 22, 35, 1200, 'I,II,III,IV', 2013,
     'Very early maturing high-yield variety'),

    ('V09', 'NSIC Rc300', 'NSIC Rc300 (Tubigan 27)',    'irrigated_lowland', 'Dry/Wet', 108, 5.8, 9.0,
     92, 'slender', 20.5, 'low', 'low', 'moderate',
     'BPH', 'BB, blast', 22, 35, 1200, 'I,II,III,IV', 2015,
     'Salinity tolerant variant'),

    ('V10', 'NSIC Rc480', 'NSIC Rc480 (Tubigan 29)',    'irrigated_lowland', 'Dry/Wet', 106, 6.0, 9.2,
     90, 'slender', 19.0, 'low', 'low', 'low',
     'BPH,GLH', 'BB, blast, sheath blight', 22, 35, 1200, 'I,II,III,IV', 2018,
     'Latest high-yield Tubigan series'),

    ('V11', 'NSIC Rc354', 'NSIC Rc354 (Sahod Ulan 11)','rainfed_lowland',   'Wet',     115, 4.2, 6.5,
     107, 'medium', 25.0, 'high', 'high', 'low',
     'BPH', 'BB', 21, 33, 1400, 'III,IV', 2017,
     'Dual tolerance: submergence + drought'),

    ('V12', 'NSIC Rc18',  'NSIC Rc18 (Mestizo 1)',     'upland',            'Dry',     110, 3.8, 5.8,
     115, 'bold', 28.0, 'low', 'high', 'low',
     'stem borer', 'blast', 18, 32, 900, 'III,IV', 1998,
     'Good adaptation to hilly upland areas'),

    ('V13', 'NSIC Rc106', 'NSIC Rc106 (NERICA 4)',     'upland',            'Dry',     95,  3.2, 5.0,
     100, 'medium', 23.0, 'low', 'high', 'low',
     'blast', 'blast', 18, 32, 900, 'III,IV', 2004,
     'Africa-origin NERICA, early upland variety'),

    ('V14', 'NSIC Rc164', 'NSIC Rc164 (Sahod Ulan 3)', 'rainfed_lowland',   'Wet',     122, 3.9, 5.9,
     110, 'slender', 24.0, 'moderate', 'low', 'low',
     'BPH', 'BB', 22, 33, 1500, 'III,IV', 2005,
     'Tolerant to partial submergence'),

    ('V15', 'NSIC Rc436', 'NSIC Rc436 (Tubigan 28)',    'irrigated_lowland', 'Dry/Wet', 107, 5.9, 9.1,
     91, 'slender', 20.0, 'low', 'low', 'moderate',
     'BPH', 'BB, blast', 22, 35, 1200, 'I,II,III,IV', 2017,
     'Salinity and drought tolerant irrigated variety'),

    ('V16', 'NSIC Rc402', 'NSIC Rc402 (Sahod Ulan 10)','rainfed_lowland',   'Wet',     119, 4.1, 6.3,
     106, 'medium', 24.5, 'high', 'moderate', 'low',
     'BPH,GLH', 'BB', 22, 34, 1400, 'II,III,IV', 2016,
     'Sub1 gene with improved blast resistance'),

    ('V17', 'NSIC Rc160', 'NSIC Rc160-2 (Tubigan 7-2)','irrigated_lowland', 'Dry/Wet', 114, 5.3, 8.2,
     101, 'slender', 23.5, 'low', 'low', 'low',
     'BPH', 'BB', 22, 35, 1200, 'I,II,III,IV', 2006,
     'Improved line of Tubigan 7'),
]

GROWTH_STAGES = [
    # stage_no, bbch_min, bbch_max, name, days_min_paddy, days_max_paddy, days_min_upland, days_max_upland, what_to_do, water_management
    (1,  0,  9,  'Germination & Seedling',      0,   7,   0,   7,
     'Prepare seedbed. Sow pre-germinated seeds at 40–50 g/m². Apply starter fertilizer.',
     'Keep seedbed moist. Avoid waterlogging during germination.'),
    (2,  10, 19, 'Seedling Stage',               7,   21,  7,   14,
     'Monitor for damping-off disease. Thin excess seedlings if direct seeded.',
     'Maintain 2–3 cm standing water for paddy. Keep moist for upland.'),
    (3,  20, 29, 'Tillering',                   21,  42,  14,  35,
     'Apply 1st split of fertilizer (Basal). Control weeds (hand weed or herbicide).',
     'Maintain 5 cm standing water. Mid-season drain once to boost tillering.'),
    (4,  30, 39, 'Stem Elongation',              42,  60,  35,  55,
     'Monitor for stem borer. Apply 2nd split of nitrogen fertilizer.',
     'Maintain 5–10 cm standing water continuously.'),
    (5,  40, 49, 'Booting',                      60,  75,  55,  70,
     'Apply 3rd fertilizer split (panicle initiation). Scout for rice bug.',
     'Maintain 5–10 cm water level. Critical period — do not drain.'),
    (6,  50, 59, 'Heading / Flowering',          75,  85,  70,  80,
     'Monitor for blast and bacterial blight. Spray fungicide if blast detected.',
     'Maintain 5 cm water. Avoid drought stress — most critical water stage.'),
    (7,  60, 69, 'Grain Filling',                85,  100, 80,  95,
     'Apply foliar micronutrients if crop yellowing observed. Monitor grain pests.',
     'Maintain 2–3 cm water until grain is 80% filled.'),
    (8,  70, 79, 'Ripening / Maturity',         100, 115, 95,  110,
     'Drain field 7–10 days before harvest. Prepare harvesting equipment.',
     'Drain field completely 7–10 days before expected harvest date.'),
    (9,  80, 89, 'Harvesting',                  113, 125, 105, 120,
     'Harvest when 80–85% of grains are straw-colored. Use combine or manual harvest.',
     'Field should be dry. Ensure machinery can access without getting stuck.'),
    (10, 90, 99, 'Post-Harvest',                125, 135, 120, 130,
     'Dry grains to 14% moisture. Store in clean, dry bags. Prepare land for next cycle.',
     'Flood fallow field if possible to suppress soil-borne diseases.'),
]

FERTILIZER_SCHEDULE = [
    # app_no, stage_name, days_after_transplanting, fertilizer, rate_kg_ha, method, notes
    (1, 'Basal Application',          '0 DAT',      'Complete fertilizer (14-14-14)',
     '200 kg/ha', 'Broadcast and incorporate before transplanting',
     'Apply 1–2 days before transplanting or incorporate at final land preparation.'),
    (2, 'Active Tillering',           '21–25 DAT',  'Urea (46-0-0)',
     '50 kg/ha', 'Broadcast between hills',
     'Apply when majority of tillers have emerged. Avoid flooding immediately after.'),
    (3, 'Panicle Initiation',         '40–45 DAT',  'Urea (46-0-0) + Muriate of Potash (0-0-60)',
     '50 kg/ha Urea + 30 kg/ha MOP', 'Broadcast between hills',
     'Critical application — promotes grain filling and reduces sterility.'),
    (4, 'Heading / Grain Fill',       '70–75 DAT',  'Foliar micronutrient spray (Zinc, Boron)',
     '2 L/ha foliar', 'Spray application',
     'Apply only if deficiency symptoms visible (yellowing, white tips). Optional.'),
]

PESTS_DISEASES = [
    # type, common_name, scientific_name, stage_affected, symptoms, control
    ('pest', 'Rice Stem Borer',
     'Chilo suppressalis / Scirpophaga incertulas',
     'Tillering to Heading',
     'Dead hearts (young plant wilts), whiteheads (late stage — empty panicles). Frass inside stems.',
     'Use resistant varieties. Apply carbofuran 3G at 17 kg/ha at tillering. Destroy stubble after harvest.'),

    ('pest', 'Brown Planthopper (BPH)',
     'Nilaparvata lugens',
     'All vegetative stages',
     'Hopperburn — circular patches of yellowing/brown plants. Honeydew secretion causes sooty mold.',
     'Use BPH-resistant varieties (NSIC Rc222, Rc238). Avoid excessive nitrogen. Apply imidacloprid if > 2 hoppers/hill.'),

    ('pest', 'Green Leafhopper (GLH)',
     'Nephotettix virescens',
     'Seedling to Tillering',
     'Yellowing of leaf tips. Primary vector of Tungro virus disease.',
     'Use GLH/Tungro-resistant varieties. Roguing infected plants. Apply insecticide only when > 5 GLH/hill.'),

    ('pest', 'Rice Bug',
     'Leptocorisa oratorius',
     'Heading to Grain Fill',
     'Empty or chalky grains. Panicles show floret damage. Foul smell from feeding.',
     'Plant synchronously to reduce crop duration overlap. Sweep net monitoring. Apply malathion if > 1 bug/10 hills.'),

    ('pest', 'Rice Whorl Maggot',
     'Hydrellia philippina',
     'Seedling to Tillering',
     'Tubular rolling of youngest leaf. Feeding marks on rolled leaf. Leaf tip turning white.',
     'Natural enemies (parasitoid wasps) usually sufficient. Drain field for 3–4 days at early tillering.'),

    ('pest', 'Rice Black Bug',
     'Scotinophara coarctata',
     'All growth stages',
     'Deadheart, bugburn, and roundspot symptoms. Plants appear scorched.',
     'Resistant varieties. Avoid ratoon crops. Destroy weed hosts. Apply carbosulfan if infestation > 0.5 bug/hill.'),

    ('disease', 'Rice Blast',
     'Pyricularia oryzae',
     'Seedling to Heading',
     'Diamond/spindle-shaped lesions with gray centers and brown borders on leaves. Neck rot at heading (panicle blast).',
     'Plant resistant varieties. Avoid excessive N. Apply tricyclazole (Beam) or isoprothiolane (Fujione) at early lesion.'),

    ('disease', 'Bacterial Leaf Blight (BB)',
     'Xanthomonas oryzae pv. oryzae',
     'Tillering to Heading',
     'Water-soaked to yellow lesions starting from leaf margins. Lesions turn white/gray and dry out.',
     'Use BB-resistant varieties (Rc222, Rc300). Avoid excessive nitrogen. No effective chemical control — prevention is key.'),

    ('disease', 'Sheath Blight',
     'Rhizoctonia solani',
     'Tillering to Grain Fill',
     'Oval/elliptical lesions on leaf sheath with grayish-green center and brown margin. High humidity worsens it.',
     'Reduce plant density. Avoid excessive N. Apply hexaconazole (Anvil) or validamycin (Validacin) at early infection.'),

    ('disease', 'Rice Tungro',
     'Rice Tungro Spherical Virus (RTSV) + Rice Tungro Bacilliform Virus (RTBV)',
     'Seedling to Tillering',
     'Yellowing and orange discoloration starting from leaf tip. Stunted plant growth. Vector: Green Leafhopper.',
     'Plant Tungro-resistant varieties. Control GLH vector. Roguing and destroy infected plants. Synchronous planting.'),

    ('disease', 'False Smut',
     'Ustilaginoidea virens',
     'Heading to Maturity',
     'Individual florets transformed into dark greenish-black spore balls. Rare but reduces grain count.',
     'Use clean certified seeds. Proper spacing. Apply propiconazole (Tilt) at 50% heading if pressure high.'),

    ('disease', 'Brown Spot',
     'Helminthosporium oryzae',
     'Seedling to Ripening',
     'Small oval/circular brown spots with yellow halo on leaves and glumes. Associated with nutrient-poor soils.',
     'Improve soil fertility (fix K and Zn deficiencies). Use certified seeds. Apply mancozeb if severe.'),

    ('disease', 'Narrow Brown Leaf Spot',
     'Cercospora janseana',
     'Tillering to Grain Fill',
     'Narrow brown linear streaks on leaf blade parallel to midrib.',
     'Use balanced fertilization. Apply fungicide only if > 25% leaf area affected.'),
]


class Command(BaseCommand):
    help = 'Load seed data: rice varieties, growth stages, fertilizer schedule, pests/diseases'

    def handle(self, *args, **options):
        self._load_varieties()
        self._load_growth_stages()
        self._load_fertilizer()
        self._load_pests()
        self._create_demo_user()
        self.stdout.write(self.style.SUCCESS('Seed data loaded successfully.'))

    def _create_demo_user(self):
        User = get_user_model()
        demo_email = 'demo@riceflow.ph'
        if not User.objects.filter(email=demo_email).exists():
            user = User.objects.create_user(
                username='demo_farmer',
                email=demo_email,
                password='demo1234',
                first_name='Demo',
                last_name='Farmer',
            )
            user.phone        = '09000000000'
            user.barangay     = 'San Francisco'
            user.municipality = 'Panabo City'
            user.province     = 'Davao del Norte'
            user.save()
            self.stdout.write('  Demo user created: demo@riceflow.ph / demo1234')
        else:
            self.stdout.write('  Demo user already exists')

    def _load_varieties(self):
        created_count = 0
        for row in VARIETIES:
            (vid, nsic, name, eco, season, mat, avg_y, max_y, ht, grain, amyl,
             sub, drg, sal, pest_r, dis_r, tmin, tmax, rain_min, pagasa, yr, notes) = row
            _, created = RiceVariety.objects.update_or_create(
                variety_id=vid,
                defaults=dict(
                    nsic_code=nsic, common_name=name, ecosystem=eco, season=season,
                    maturity_days=mat, avg_yield_t_ha=avg_y, max_yield_t_ha=max_y,
                    plant_height_cm=ht, grain_type=grain, amylose_pct=amyl,
                    submergence_tolerance=sub, drought_tolerance=drg, salinity_tolerance=sal,
                    pest_resistance=pest_r, disease_resistance=dis_r,
                    optimal_temp_min=tmin, optimal_temp_max=tmax,
                    optimal_rainfall_min=rain_min, pagasa_climate_types=pagasa,
                    year_released=yr, notes=notes, is_active=True,
                )
            )
            if created:
                created_count += 1
        self.stdout.write(f'  Varieties: {len(VARIETIES)} processed, {created_count} new')

    def _load_growth_stages(self):
        created_count = 0
        for row in GROWTH_STAGES:
            stage_no, bmin, bmax, name, dpmin, dpmax, dumin, dumax, what, water = row
            _, created = GrowthStage.objects.update_or_create(
                stage_no=stage_no,
                defaults=dict(
                    bbch_min=bmin, bbch_max=bmax, name=name,
                    days_min_paddy=dpmin, days_max_paddy=dpmax,
                    days_min_upland=dumin, days_max_upland=dumax,
                    what_to_do=what, water_management=water,
                )
            )
            if created:
                created_count += 1
        self.stdout.write(f'  Growth stages: {len(GROWTH_STAGES)} processed, {created_count} new')

    def _load_fertilizer(self):
        created_count = 0
        for row in FERTILIZER_SCHEDULE:
            app_no, stage_name, dat, fertilizer, rate, method, notes = row
            _, created = FertilizerSchedule.objects.update_or_create(
                app_no=app_no,
                defaults=dict(
                    stage_name=stage_name, days_after_transplanting=dat,
                    fertilizer=fertilizer, rate_kg_ha=rate, method=method, notes=notes,
                )
            )
            if created:
                created_count += 1
        self.stdout.write(f'  Fertilizer schedule: {len(FERTILIZER_SCHEDULE)} processed, {created_count} new')

    def _load_pests(self):
        created_count = 0
        for row in PESTS_DISEASES:
            ptype, cname, sname, stage, symptoms, control = row
            _, created = PestDisease.objects.update_or_create(
                common_name=cname,
                defaults=dict(
                    type=ptype, scientific_name=sname, stage_affected=stage,
                    symptoms=symptoms, control=control,
                )
            )
            if created:
                created_count += 1
        self.stdout.write(f'  Pests & diseases: {len(PESTS_DISEASES)} processed, {created_count} new')
