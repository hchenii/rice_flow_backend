from datetime import timedelta, datetime
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import PlantingGuide, GuideStep
from .serializers import PlantingGuideSerializer, GuideStepSerializer, GuideStepUpdateSerializer
from apps.farms.models import Farm
from apps.varieties.models import RiceVariety, GrowthStage
from apps.recommendations.models import Recommendation

import os
import json
import requests

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
# Using the lite model — 1000 req/day on free tier (vs 50/day for full flash).
# If you ever need richer output, swap back to 'gemini-2.5-flash:generateContent'.
GEMINI_URL = (
    'https://generativelanguage.googleapis.com/v1beta/models/'
    'gemini-2.5-flash-lite:generateContent'
)
GUIDE_CATEGORIES = ['planting', 'fertilizer', 'pest_prevention', 'irrigation', 'harvesting']

# ── Persisted-guide response shape ─────────────────────────────────────────────
# Steps are saved as GuideStep rows; responses carry the real DB id so the
# mobile app's completion sync (PATCH steps/<id>/complete/) targets real rows.

def _step_dict(st):
    return {
        'id':                st.id,
        'stepNumber':        st.step_no,
        'title':             st.title,
        'instruction':       st.description,
        'daysAfterPlanting': st.days_after_planting if st.days_after_planting is not None else 0,
        'category':          st.category or 'planting',
        'is_completed':      st.is_completed,
    }

def _guide_response(guide, source):
    steps = [
        _step_dict(st)
        for st in guide.steps.order_by('days_after_planting', 'step_no')
    ]
    return {
        'id':         guide.id,
        'farm':       guide.farm_id,
        'variety':    guide.variety_id,
        'season':     guide.season,
        'language':   guide.language,
        'start_date': guide.start_date.isoformat() if guide.start_date else None,
        'source':     source,
        'steps':      steps,
    }


# ── Open-Meteo 7-day forecast for the farm's coords ────────────────────────────
def _get_forecast(lat, lng):
    """Fetch next 7 days of daily rainfall + temp range from Open-Meteo (free, no key)."""
    if lat is None or lng is None:
        return []
    try:
        r = requests.get(
            'https://api.open-meteo.com/v1/forecast',
            params={
                'latitude':  lat,
                'longitude': lng,
                'daily':     'temperature_2m_max,temperature_2m_min,precipitation_sum',
                'forecast_days': 7,
                'timezone':  'Asia/Manila',
            },
            timeout=8,
        )
        r.raise_for_status()
        d = r.json().get('daily', {})
        times = d.get('time', [])
        tmax  = d.get('temperature_2m_max', [])
        tmin  = d.get('temperature_2m_min', [])
        rain  = d.get('precipitation_sum', [])
        out = []
        for i, day in enumerate(times):
            out.append({
                'date': day,
                'rain': rain[i] if i < len(rain) else 0,
                'tmin': tmin[i] if i < len(tmin) else None,
                'tmax': tmax[i] if i < len(tmax) else None,
            })
        return out
    except Exception:
        return []


VALID_GUIDE_LANGS = {'en', 'fil', 'ceb'}


def _format_forecast(forecast):
    """Format forecast list into a single human-readable string for the prompt + console."""
    if not forecast:
        return 'no forecast'
    parts = []
    for f in forecast:
        rain = f.get('rain') or 0
        tmin = f.get('tmin')
        tmax = f.get('tmax')
        if tmin is not None and tmax is not None:
            parts.append(f"{f['date']}: {rain:.1f}mm rain, {tmin:.1f}-{tmax:.1f}C")
        else:
            parts.append(f"{f['date']}: {rain:.1f}mm rain")
    return '; '.join(parts)


def _format_logs(logs):
    """Format farmer log array into a multi-line string the prompt + console can show."""
    if not logs:
        return 'no logs yet'
    lines = []
    for l in logs:
        if not isinstance(l, dict):
            continue
        date   = l.get('logDate') or l.get('log_date') or ''
        stage  = l.get('growthStage') or l.get('growth_stage') or '—'
        issue  = l.get('observedIssue') or l.get('observed_issue') or l.get('issue_type') or 'None'
        action = l.get('actionTaken') or l.get('action_taken') or 'None'
        notes  = (l.get('notes') or l.get('observation') or '').strip()
        sev    = l.get('severity') or ''
        sev_part = f" [{sev}]" if sev else ''
        lines.append(f"- {date} ({stage}): {issue}{sev_part}. Action: {action}. Notes: {notes}")
    return '\n'.join(lines)


# ── Single-step generation: ask Gemini for ONE follow-up step in a category. ──
# Used by the "check a step → reveal a fresh one at the bottom" flow on mobile.
def _generate_one_step(variety, scan, logs, forecast, language, category, last_day, base_index):
    """Ask Gemini for a single new follow-up step in the given category, dated after `last_day`."""
    if not GEMINI_API_KEY:
        return None

    field = (
        f"soil texture: {getattr(scan, 'soil_texture', '') or 'clay loam'}, "
        f"soil pH: {getattr(scan, 'soil_ph', None) or 6.2}, "
        f"flood risk: {getattr(scan, 'flood_risk', '') or 'Low'}, "
        f"avg temperature: {getattr(scan, 'avg_temperature', None) or 27} C"
    ) if scan else "typical irrigated lowland conditions in Panabo City"

    forecast_str = _format_forecast(forecast)
    logs_str     = _format_logs(logs)

    if language == 'fil':
        lang_directive = (
            "Use a short Filipino (Tagalog) title and a 1-2 sentence Filipino instruction "
            "(with specific quantities/timing). Use plain Filipino any smallholder farmer can follow.\n"
            'Example shape: {"title":"Pangalawang Pataba","instruction":"Maglagay ng urea 1 sako/ha.","daysAfterPlanting":40,"category":"fertilizer"}'
        )
    elif language == 'ceb':
        lang_directive = (
            "Use a short light Bisaya (Cebuano) title and a 1-2 sentence Bisaya instruction "
            "(with specific quantities/timing). Use easy Bisaya — avoid deep Cebuano words.\n"
            'Example shape: {"title":"Ikaduhang Abono","instruction":"Butangi og urea 1 ka sako/ha.","daysAfterPlanting":40,"category":"fertilizer"}'
        )
    else:
        lang_directive = (
            "Use a short English title and a 1-2 sentence English instruction "
            "(with specific quantities/timing). Plain English a smallholder farmer can follow.\n"
            'Example shape: {"title":"Second Top-dressing","instruction":"Apply urea at 1 bag/ha.","daysAfterPlanting":40,"category":"fertilizer"}'
        )

    prompt = (
        "You are a Philippine rice agronomist creating ONE follow-up planting-guide step "
        "for a smallholder farmer in Panabo City, Davao del Norte who just finished an "
        f"earlier {category} step and needs the next concrete action.\n\n"
        f"Rice variety: {variety.common_name} ({variety.ecosystem}), matures in "
        f"{variety.maturity_days} days, average yield {variety.avg_yield_t_ha} t/ha.\n"
        f"Field conditions: {field}.\n\n"
        f"Next 7 days weather forecast: {forecast_str}.\n\n"
        f"Recent farmer observations:\n{logs_str}\n\n"
        f"REQUIRED CATEGORY for the new step: {category}.\n"
        f"REQUIRED daysAfterPlanting: an integer STRICTLY GREATER THAN {last_day} so the "
        "new step appears AFTER the just-finished one. Pick a sensible timing for this category.\n"
        "Do not repeat any step the farmer has already done — pick a new, concrete next action.\n\n"
        f"{lang_directive}\n\n"
        "OUTPUT FORMAT — return ONLY valid JSON, no markdown, no code fences. "
        "Start with `{` and end with `}`. Use this exact shape:\n"
        '{"title":"...","instruction":"...","daysAfterPlanting":N,"category":"' + category + '"}'
    )

    payload = {
        'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
        'generationConfig': {
            'temperature': 0.6,
            'maxOutputTokens': 400,
            'thinkingConfig': {'thinkingBudget': 0},
        },
    }

    try:
        resp = requests.post(f'{GEMINI_URL}?key={GEMINI_API_KEY}', json=payload, timeout=25)
        if resp.status_code != 200:
            print(f'[PLANTING GUIDE/append] ✗ Gemini non-200: {resp.text[:400]}', flush=True)
            return None
        body = resp.json()
        text = (body.get('candidates') or [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        # Tolerant JSON parsing — same defensive pattern as _generate_ai_steps
        parsed = None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            cleaned = text.strip()
            if cleaned.startswith('```'):
                cleaned = cleaned.split('\n', 1)[-1] if '\n' in cleaned else cleaned[3:]
                if cleaned.startswith('json'):
                    cleaned = cleaned[4:].lstrip('\n')
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3].rstrip()
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                import re
                m = re.search(r'\{[\s\S]*\}', text)
                if m:
                    try:
                        parsed = json.loads(m.group(0))
                    except json.JSONDecodeError:
                        return None
                else:
                    return None

        cat = parsed.get('category')
        if cat not in GUIDE_CATEGORIES:
            return None
        day = int(parsed.get('daysAfterPlanting', last_day + 7))
        # Enforce that the new step lands strictly after the one the farmer just finished
        if day <= last_day:
            day = last_day + 7

        return {
            'id':                f'step_{base_index:03d}',
            'stepNumber':        base_index,
            'title':             str(parsed.get('title', '')).strip(),
            'instruction':       str(parsed.get('instruction', '')).strip(),
            'daysAfterPlanting': day,
            'category':          cat,
        }
    except Exception as e:
        print(f'[PLANTING GUIDE/append] ✗ {type(e).__name__}: {e}', flush=True)
        return None


# ── Gemini call — uses variety + scan + logs + forecast for adaptive guidance ──
def _generate_ai_steps(variety, scan, logs, forecast, language='en'):
    """Ask Gemini for a personalized planting guide that adapts to the farmer's logs + weather."""
    if not GEMINI_API_KEY:
        print('[PLANTING GUIDE] ✗ GEMINI_API_KEY not set in environment — cannot call Gemini', flush=True)
        return []
    print(f'[PLANTING GUIDE] ✓ GEMINI_API_KEY present (len={len(GEMINI_API_KEY)}, starts with {GEMINI_API_KEY[:6]}...)', flush=True)

    field = (
        f"soil texture: {getattr(scan, 'soil_texture', '') or 'clay loam'}, "
        f"soil pH: {getattr(scan, 'soil_ph', None) or 6.2}, "
        f"seasonal rainfall: {getattr(scan, 'seasonal_rainfall_mm', None) or 1200} mm, "
        f"flood risk: {getattr(scan, 'flood_risk', '') or 'Low'}, "
        f"elevation: {getattr(scan, 'elevation_m', None) or 45} m, "
        f"avg temperature: {getattr(scan, 'avg_temperature', None) or 27} C"
    ) if scan else "typical irrigated lowland conditions in Panabo City"

    forecast_str = _format_forecast(forecast)
    logs_str     = _format_logs(logs)

    # Language-specific instructions for the output text fields.
    if language == 'fil':
        lang_directive = (
            "Each step needs a short Filipino (Tagalog) title and a 1-2 sentence "
            "Filipino instruction (with specific quantities/timing). Use simple "
            "Filipino that an ordinary smallholder farmer can understand.\n"
            'Example shape: {"stepNumber":1,"title":"Paghahanda ng Lupa","instruction":"Araruhin ng dalawang ulit.","daysAfterPlanting":-15,"category":"planting"}'
        )
    elif language == 'ceb':
        lang_directive = (
            "Each step needs a short Bisaya (Cebuano) title and a 1-2 sentence "
            "Bisaya instruction (with specific quantities/timing). Use light, easy "
            "Bisaya that an ordinary smallholder farmer can understand — avoid deep "
            "or rarely used Cebuano words.\n"
            'Example shape: {"stepNumber":1,"title":"Pag-andam sa Yuta","instruction":"Daro-a sa duha ka higayon.","daysAfterPlanting":-15,"category":"planting"}'
        )
    else:  # en
        lang_directive = (
            "Each step needs a short English title and a 1-2 sentence English "
            "instruction (with specific quantities/timing). Use plain English that "
            "an ordinary smallholder farmer can understand.\n"
            'Example shape: {"stepNumber":1,"title":"Land Preparation","instruction":"Plow the field twice.","daysAfterPlanting":-15,"category":"planting"}'
        )

    prompt = (
        "You are a Philippine rice agronomist creating a personalized planting guide "
        "for a smallholder farmer in Panabo City, Davao del Norte.\n\n"
        f"Rice variety: {variety.common_name} ({variety.ecosystem}), matures in "
        f"{variety.maturity_days} days, average yield {variety.avg_yield_t_ha} t/ha, "
        f"submergence tolerance {variety.submergence_tolerance}, drought tolerance "
        f"{variety.drought_tolerance}.\n"
        f"Field conditions: {field}.\n\n"
        f"Next 7 days weather forecast: {forecast_str}.\n\n"
        f"Recent farmer observations:\n{logs_str}\n\n"
        "TASK: Produce 8-12 concrete guide steps tailored to THIS variety AND the field "
        "conditions AND the upcoming weather AND the farmer's recent observations.\n"
        "- If farmer logged pest sightings → add specific pest_prevention steps for that exact pest.\n"
        "- If logs mention yellowing leaves or nutrient deficiency → add a fertilizer adjustment.\n"
        "- If forecast shows heavy rain → add drainage or delay the next fertilizer.\n"
        "- If logs mention drought → add irrigation steps.\n\n"
        f"{lang_directive}\n\n"
        "Order steps by daysAfterPlanting (negative numbers = before planting).\n\n"
        "OUTPUT FORMAT — return ONLY valid JSON, no markdown, no code fences, no explanation. "
        "Start with `{` and end with `}`. Use this exact shape:\n"
        '{"steps":[{"stepNumber":1,"title":"...","instruction":"...","daysAfterPlanting":-15,"category":"planting"}]}\n\n'
        "Allowed categories (use exactly one of these strings per step): "
        "planting, fertilizer, pest_prevention, irrigation, harvesting."
    )

    payload = {
        'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
        'generationConfig': {
            'temperature': 0.5,
            'maxOutputTokens': 2048,
            'thinkingConfig': {'thinkingBudget': 0},
        },
    }

    resp = None
    try:
        print(f'[PLANTING GUIDE] → POST {GEMINI_URL} (prompt={len(prompt)} chars, logs={len(logs)}, forecast_days={len(forecast)})', flush=True)
        resp = requests.post(f'{GEMINI_URL}?key={GEMINI_API_KEY}', json=payload, timeout=40)
        print(f'[PLANTING GUIDE] ← Gemini HTTP {resp.status_code} (body size: {len(resp.text)} bytes)', flush=True)

        if resp.status_code != 200:
            # Show the actual error body so we can diagnose 400/401/429/500 fast
            print(f'[PLANTING GUIDE] ✗ Gemini non-200 body: {resp.text[:800]}', flush=True)
            return []

        body = resp.json()
        candidates = body.get('candidates') or []
        if not candidates:
            print(f'[PLANTING GUIDE] ✗ No candidates in Gemini response: {json.dumps(body)[:600]}', flush=True)
            return []

        # Gemini sometimes returns a finishReason like "MAX_TOKENS" or "SAFETY"
        finish = candidates[0].get('finishReason')
        if finish and finish not in ('STOP', 'MAX_TOKENS'):
            print(f'[PLANTING GUIDE] ✗ Gemini finishReason={finish}', flush=True)

        parts = candidates[0].get('content', {}).get('parts') or []
        if not parts:
            print(f'[PLANTING GUIDE] ✗ No content parts in candidate: {json.dumps(candidates[0])[:400]}', flush=True)
            return []
        text = parts[0].get('text', '')

        # Lenient parsing — Gemini in text mode sometimes wraps JSON in ```json
        # code fences or adds a leading sentence. Try plain parse first, then
        # strip fences, then regex-extract the {...} block as last resort.
        parsed = None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            cleaned = text.strip()
            # Remove leading ```json or ``` and trailing ```
            if cleaned.startswith('```'):
                cleaned = cleaned.split('\n', 1)[-1] if '\n' in cleaned else cleaned[3:]
                if cleaned.startswith('json'):
                    cleaned = cleaned[4:].lstrip('\n')
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3].rstrip()
            try:
                parsed = json.loads(cleaned)
                print('[PLANTING GUIDE] · parsed after stripping code fences', flush=True)
            except json.JSONDecodeError:
                # Last resort: find first { and last } and parse what's between
                import re
                m = re.search(r'\{[\s\S]*\}', text)
                if m:
                    try:
                        parsed = json.loads(m.group(0))
                        print('[PLANTING GUIDE] · parsed after regex extraction', flush=True)
                    except json.JSONDecodeError as je2:
                        print(f'[PLANTING GUIDE] ✗ All JSON parse attempts failed: {je2}. Text preview: {text[:400]}', flush=True)
                        return []
                else:
                    print(f'[PLANTING GUIDE] ✗ No JSON object found in response. Text preview: {text[:400]}', flush=True)
                    return []

        raw_steps = parsed.get('steps', [])
        print(f'[PLANTING GUIDE] ✓ Gemini returned {len(raw_steps)} raw steps', flush=True)

        out, rejected = [], 0
        for i, st in enumerate(raw_steps, start=1):
            if st.get('category') not in GUIDE_CATEGORIES:
                rejected += 1
                print(f'[PLANTING GUIDE] · rejected step {i} (unknown category={st.get("category")!r}): {st.get("title")!r}', flush=True)
                continue
            out.append({
                'id':                f'step_{i:03d}',
                'stepNumber':        st.get('stepNumber', i),
                'title':             str(st.get('title', '')).strip(),
                'instruction':       str(st.get('instruction', '')).strip(),
                'daysAfterPlanting': int(st.get('daysAfterPlanting', 0)),
                'category':          st['category'],
            })

        print(f'[PLANTING GUIDE] ✓ Accepted {len(out)} steps (rejected {rejected})', flush=True)
        return out

    except requests.Timeout:
        print('[PLANTING GUIDE] ✗ Gemini timeout (>40s)', flush=True)
        return []
    except requests.ConnectionError as ce:
        print(f'[PLANTING GUIDE] ✗ Network error reaching Gemini: {ce}', flush=True)
        return []
    except Exception as e:
        import traceback
        print(f'[PLANTING GUIDE] ✗ Unexpected error: {type(e).__name__}: {e}', flush=True)
        print(traceback.format_exc(), flush=True)
        if resp is not None:
            print(f'[PLANTING GUIDE] Last response: {resp.text[:400]}', flush=True)
        return []


def _fallback_steps(language='en'):
    """Template fallback used if Gemini is unavailable. Returns English steps by default
    so the user sees something usable when the AI service is down."""

    # English fallback that doesn't depend on whatever language the GrowthStage rows
    # were originally seeded in. Static and stable — keeps the demo defendable.
    en_template = [
        ('Land Preparation',      'Plow the field twice and level it. Drain old water and remove weeds.', -15, 'planting'),
        ('Seedbed Preparation',   'Prepare a 1m-wide seedbed with fine, fertile soil for the seedlings.', -10, 'planting'),
        ('Sowing',                'Sow pre-germinated seeds evenly on the seedbed and keep it moist.', -7, 'planting'),
        ('Transplanting',         'Transplant 20-25 day old seedlings at 20×20 cm spacing.', 0, 'planting'),
        ('Basal Fertilizer',      'Apply complete fertilizer (14-14-14) at 5 bags/ha before transplanting.', 0, 'fertilizer'),
        ('First Water Management', 'Maintain 2-3 cm shallow water level for the first 2 weeks.', 3, 'irrigation'),
        ('Top-dressing (Tillering)', 'Apply urea (46-0-0) at 2 bags/ha to support active tillering.', 20, 'fertilizer'),
        ('Pest Monitoring',       'Scout for stem borer and rice bug; treat only when threshold is reached.', 30, 'pest_prevention'),
        ('Panicle Initiation Fertilizer', 'Apply urea (46-0-0) at 1 bag/ha when panicle starts forming.', 45, 'fertilizer'),
        ('Drain Before Harvest',  'Drain the field 7-10 days before planned harvest date for easier harvesting.', 95, 'irrigation'),
        ('Harvesting',            'Harvest when 80-85% of grains turn golden. Threshing should follow within 24 hours.', 105, 'harvesting'),
    ]

    titles_fil = {
        'Land Preparation':              'Paghahanda ng Lupa',
        'Seedbed Preparation':           'Paghahanda ng Punlaan',
        'Sowing':                        'Pagpupunla',
        'Transplanting':                 'Paglilipat ng Punla',
        'Basal Fertilizer':              'Unang Pataba',
        'First Water Management':        'Patubig sa Simula',
        'Top-dressing (Tillering)':      'Pataba sa Pagsibol',
        'Pest Monitoring':               'Pagbabantay sa Peste',
        'Panicle Initiation Fertilizer': 'Pataba sa Pagbutil',
        'Drain Before Harvest':          'Patuyo Bago Mag-ani',
        'Harvesting':                    'Pag-aani',
    }
    titles_ceb = {
        'Land Preparation':              'Pag-andam sa Yuta',
        'Seedbed Preparation':           'Pag-andam sa Punlaan',
        'Sowing':                        'Pagsabwag',
        'Transplanting':                 'Pagbalhin sa Punla',
        'Basal Fertilizer':              'Unang Pataba',
        'First Water Management':        'Tubig sa Sinugdanan',
        'Top-dressing (Tillering)':      'Pataba sa Pagtubo',
        'Pest Monitoring':               'Pagbantay sa Peste',
        'Panicle Initiation Fertilizer': 'Pataba sa Pagbunga',
        'Drain Before Harvest':          'Pahubsa Sa Wala Pa Ani',
        'Harvesting':                    'Pag-ani',
    }

    instr_fil = {
        'Land Preparation':              'Araruhin nang dalawang beses at patagin. Patuluin ang lumang tubig at alisin ang damo.',
        'Seedbed Preparation':           'Maghanda ng 1m ang lapad na punlaan na may pinong lupa para sa mga binhi.',
        'Sowing':                        'Magpunla ng pinatubo nang binhi nang pantay-pantay at panatilihing basa.',
        'Transplanting':                 'Ilipat ang 20-25 araw na punla sa 20×20 cm na pagitan.',
        'Basal Fertilizer':              'Maglagay ng 14-14-14 fertilizer na 5 sako/ektarya bago ilipat.',
        'First Water Management':        'Panatilihin ang 2-3 cm na tubig sa unang 2 linggo.',
        'Top-dressing (Tillering)':      'Maglagay ng urea (46-0-0) na 2 sako/ektarya para sa malusog na pagsibol.',
        'Pest Monitoring':               'Magbantay sa stem borer at rice bug; gamutin lamang kapag umabot sa threshold.',
        'Panicle Initiation Fertilizer': 'Maglagay ng urea (46-0-0) na 1 sako/ektarya kapag nagsimula nang magbutil.',
        'Drain Before Harvest':          'Patuyuin ang lupa 7-10 araw bago ang ani para mas madaling anihin.',
        'Harvesting':                    'Anihin kapag 80-85% ng butil ay kulay ginto. Igiik sa loob ng 24 oras.',
    }
    instr_ceb = {
        'Land Preparation':              'Daro-a sa duha ka higayon ug patagi. Pahubsa ang daang tubig ug kuhaa ang mga sagbot.',
        'Seedbed Preparation':           'Pag-andam og 1m ang gilapdon nga punlaan nga adunay pino nga yuta para sa binhi.',
        'Sowing':                        'Isabwag ang pinatubo nga binhi nga pantay-pantay ug ipabilin nga basa.',
        'Transplanting':                 'Ibalhin ang 20-25 ka adlaw nga punla sa 20×20 cm nga gilay-on.',
        'Basal Fertilizer':              'Butangi og 14-14-14 nga 5 ka sako/ektarya sa wala pa ibalhin.',
        'First Water Management':        'Ipabilin ang 2-3 cm nga tubig sulod sa unang 2 ka semana.',
        'Top-dressing (Tillering)':      'Butangi og urea (46-0-0) nga 2 ka sako/ektarya para sa kusog nga pagtubo.',
        'Pest Monitoring':               'Bantayi ang stem borer ug rice bug; tambali lang kung pa-abot na sa threshold.',
        'Panicle Initiation Fertilizer': 'Butangi og urea (46-0-0) nga 1 ka sako/ektarya kung magsugod na magbunga.',
        'Drain Before Harvest':          'Pahubsa ang yuta 7-10 ka adlaw sa wala pa moani aron mas sayon nga moani.',
        'Harvesting':                    'Aniha kung 80-85% sa mga butil bulawanon na. Tahopa sulod sa 24 ka oras.',
    }

    out = []
    for i, (title_en, instr_en, day, cat) in enumerate(en_template, start=1):
        if language == 'fil':
            title = titles_fil.get(title_en, title_en)
            instr = instr_fil.get(title_en, instr_en)
        elif language == 'ceb':
            title = titles_ceb.get(title_en, title_en)
            instr = instr_ceb.get(title_en, instr_en)
        else:
            title = title_en
            instr = instr_en
        out.append({
            'id':                f'step_{i:03d}',
            'stepNumber':        i,
            'title':             title,
            'instruction':       instr,
            'daysAfterPlanting': day,
            'category':          cat,
        })
    return out


# ── The view ───────────────────────────────────────────────────────────────────
class GeneratePlantingGuideView(APIView):
    """Generate a personalized planting guide using Gemini, adapting to logs + weather."""
    permission_classes = [IsAuthenticated]

    def post(self, request, recommendation_id):
        try:
            rec = Recommendation.objects.select_related('farm').get(
                pk=recommendation_id, farm__user=request.user
            )
        except Recommendation.DoesNotExist:
            return Response({'detail': 'Recommendation not found.'}, status=404)

        top_result = rec.results.order_by('rank').first()
        if not top_result:
            return Response({'detail': 'No recommendation results found.'}, status=400)

        variety = top_result.variety
        farm    = rec.farm
        season  = request.data.get('season', 'Wet Season')
        language = (request.data.get('language') or 'en').lower()
        if language not in VALID_GUIDE_LANGS:
            language = 'en'

        # Inputs from the frontend payload — adaptive context for Gemini
        logs  = request.data.get('logs') or []
        force = bool(request.data.get('force_regenerate'))

        # ── Saved-steps fast path ──────────────────────────────────────────────
        # Steps are persisted as GuideStep rows so completion survives reinstalls
        # and other devices. Return the saved checklist unless the language
        # changed or the caller explicitly asks to regenerate. Adaptivity after
        # first generation comes from the append-step flow, not full regen.
        guide, _ = PlantingGuide.objects.get_or_create(
            farm=farm, variety=variety, season=season,
            defaults={'start_date': timezone.now().date(), 'language': language},
        )
        if not force and guide.language == language and guide.steps.exists():
            print(f'[PLANTING GUIDE] ⚡ SAVED steps for guide={guide.id} — skipping Gemini call', flush=True)
            return Response(_guide_response(guide, source='SAVED'), status=status.HTTP_200_OK)

        # Latest environmental scan for this farm (soil + weather + flood)
        scan = farm.environmental_scans.order_by('-id').first() if hasattr(farm, 'environmental_scans') else None

        # 7-day forecast for the farm's coords
        forecast = _get_forecast(getattr(farm, 'latitude', None), getattr(farm, 'longitude', None))

        # Console diagnostics — match the format the user expects to see in Django logs
        flood_risk = getattr(scan, 'flood_risk', None) if scan else None
        print(f'[PLANTING GUIDE] source=GEMINI | variety={variety.common_name} | flood_risk={flood_risk}', flush=True)
        print(f'[PLANTING GUIDE] forecast={_format_forecast(forecast)}', flush=True)
        print(f'[PLANTING GUIDE] logs=\n{_format_logs(logs)}', flush=True)

        # Call Gemini (with all the adaptive context + selected language)
        steps = _generate_ai_steps(variety, scan, logs, forecast, language)
        source = 'GEMINI'

        # Fall back to template only if Gemini failed
        if not steps:
            steps = _fallback_steps(language)
            source = 'FALLBACK'
            print(f'[PLANTING GUIDE] Gemini returned 0 steps — falling back to template ({language})', flush=True)

        print(f'[PLANTING GUIDE] source={source} | steps={len(steps)}', flush=True)

        # Persist the generated steps as real GuideStep rows. Completion is then
        # tracked on the row (is_completed), so it survives app reinstalls and
        # syncs across devices. Regeneration replaces the checklist wholesale —
        # a new plan is a new checklist, so completions reset by design.
        with transaction.atomic():
            guide.steps.all().delete()
            rows = []
            for idx, st in enumerate(steps, start=1):
                dap = int(st.get('daysAfterPlanting', 0))
                rows.append(GuideStep(
                    guide=guide,
                    step_no=idx,   # enumerate: Gemini stepNumbers can repeat, (guide, step_no) is unique
                    title=st.get('title', '')[:150],
                    description=st.get('instruction', ''),
                    category=st.get('category', ''),
                    days_after_planting=dap,
                    scheduled_date=(guide.start_date + timedelta(days=dap)) if guide.start_date else None,
                ))
            GuideStep.objects.bulk_create(rows)
            guide.language = language
            guide.save(update_fields=['language'])

        return Response(_guide_response(guide, source=source), status=status.HTTP_200_OK)


class AppendGuideStepView(APIView):
    """Generate ONE additional planting-guide step in the same category as a
    step the farmer just marked complete. Backs the "check → fresh step appears
    at the bottom" UX in the Planting Guide screen.

    POST body:
      {
        "category":           "fertilizer",        # required, one of GUIDE_CATEGORIES
        "last_day":           20,                  # required, daysAfterPlanting of just-finished step
        "existing_count":     8,                   # current length of latestGuide.steps
        "season":             "Wet Season",
        "language":           "en" | "fil" | "ceb",
        "logs":               [ ... recent farmer logs ... ]
      }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, recommendation_id):
        try:
            rec = Recommendation.objects.select_related('farm').get(
                pk=recommendation_id, farm__user=request.user
            )
        except Recommendation.DoesNotExist:
            return Response({'detail': 'Recommendation not found.'}, status=404)

        top_result = rec.results.order_by('rank').first()
        if not top_result:
            return Response({'detail': 'No recommendation results found.'}, status=400)

        category       = request.data.get('category')
        if category not in GUIDE_CATEGORIES:
            return Response({'detail': f'category must be one of {GUIDE_CATEGORIES}'}, status=400)

        try:
            last_day = int(request.data.get('last_day', 0))
        except (TypeError, ValueError):
            return Response({'detail': 'last_day must be an integer'}, status=400)

        existing_count = int(request.data.get('existing_count') or 0)
        language       = (request.data.get('language') or 'en').lower()
        if language not in VALID_GUIDE_LANGS:
            language = 'en'
        logs           = request.data.get('logs') or []

        variety = top_result.variety
        farm    = rec.farm
        season  = request.data.get('season', 'Wet Season')
        scan    = farm.environmental_scans.order_by('-id').first() if hasattr(farm, 'environmental_scans') else None
        forecast = _get_forecast(getattr(farm, 'latitude', None), getattr(farm, 'longitude', None))

        base_index = max(existing_count + 1, 12)
        step = _generate_one_step(
            variety, scan, logs, forecast, language, category, last_day, base_index,
        )
        if not step:
            return Response({'detail': 'Could not generate next step right now.'}, status=503)

        # Persist the new step on the farm's guide so it has a real DB id —
        # completion sync and reinstall-restore then work the same as the
        # originally generated steps.
        guide, _ = PlantingGuide.objects.get_or_create(
            farm=farm, variety=variety, season=season,
            defaults={'start_date': timezone.now().date(), 'language': language},
        )
        dap = int(step.get('daysAfterPlanting', last_day + 7))
        with transaction.atomic():
            next_no = (guide.steps.aggregate(m=Max('step_no'))['m'] or 0) + 1
            row = GuideStep.objects.create(
                guide=guide,
                step_no=next_no,
                title=str(step.get('title', ''))[:150],
                description=str(step.get('instruction', '')),
                category=step.get('category', category),
                days_after_planting=dap,
                scheduled_date=(guide.start_date + timedelta(days=dap)) if guide.start_date else None,
            )

        return Response({'step': _step_dict(row)}, status=status.HTTP_200_OK)


class PlantingGuideListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PlantingGuideSerializer

    def get_queryset(self):
        return PlantingGuide.objects.filter(farm__user=self.request.user)


class PlantingGuideDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PlantingGuideSerializer

    def get_queryset(self):
        return PlantingGuide.objects.filter(farm__user=self.request.user)


class MarkStepCompleteView(APIView):
    """Set a guide step's completion. Steps are persisted GuideStep rows, so this
    is the durable source of truth — reinstalling the app or logging in on
    another device restores check-offs from here.

    PATCH body: { "is_completed": true | false }   (defaults to true)
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, step_id):
        try:
            step = GuideStep.objects.select_related('guide__farm').get(
                pk=step_id, guide__farm__user=request.user
            )
        except GuideStep.DoesNotExist:
            return Response({'detail': 'Step not found.'}, status=404)

        done = bool(request.data.get('is_completed', True))
        step.is_completed = done
        step.completed_at = timezone.now() if done else None
        step.save(update_fields=['is_completed', 'completed_at'])
        return Response(GuideStepSerializer(step).data)
