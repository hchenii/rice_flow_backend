import os
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.varieties.models import RiceVariety

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
GEMINI_URL = (
    'https://generativelanguage.googleapis.com/v1beta/models/'
    'gemini-2.5-flash:generateContent'
)

VALID_LANGS = {'en', 'fil', 'ceb'}


def _language_label(code: str) -> str:
    return {'en': 'English', 'fil': 'Filipino (Tagalog)', 'ceb': 'Bisaya (Cebuano)'}.get(code, 'English')


def _build_system_context(language: str = 'en') -> str:
    """Build the system context: grounded in the rice variety dataset PLUS
    general rice-farming knowledge (fertilizer, pests, water, harvest). Still
    refuses non-rice / off-topic questions (other crops, politics, etc.)."""
    varieties = RiceVariety.objects.filter(is_active=True).values(
        'nsic_code', 'common_name', 'ecosystem', 'maturity_days',
        'avg_yield_t_ha', 'submergence_tolerance',
        'drought_tolerance', 'salinity_tolerance', 'notes',
    )

    variety_lines = '\n'.join([
        f"- {v.get('nsic_code', '')} {v.get('common_name', '')}: "
        f"{v.get('ecosystem', '')}, "
        f"{v.get('maturity_days', '')} days to maturity, "
        f"{v.get('avg_yield_t_ha', '')} t/ha avg yield, "
        f"submergence tolerance: {v.get('submergence_tolerance', 'unknown')}, "
        f"drought tolerance: {v.get('drought_tolerance', 'unknown')}, "
        f"salinity tolerance: {v.get('salinity_tolerance', 'unknown')}"
        for v in varieties
    ]) or "(no varieties currently in the dataset)"

    lang_label = _language_label(language)
    if language == 'fil':
        reply_instr = 'Sumagot sa Filipino (Tagalog) na simple at madaling intindihin ng isang ordinaryong magsasaka. Limitahan ang sagot sa 3–5 pangungusap.'
        refusal     = 'Pasensya na, makakasagot lang ako tungkol sa pagpapalay at sa mga uri ng palay. May maitatanong ka ba tungkol sa pataba, peste, tubig, o pag-aani?'
    elif language == 'ceb':
        reply_instr = 'Tubaga sa magaan nga Bisaya (Cebuano) — simple lang nga mga pulong nga sayon sabton sa ordinaryong mag-uuma. Limita ang tubag sa 3–5 ka pulong-pamulong.'
        refusal     = 'Pasaylo-a, makatubag lang ko bahin sa pagtanum og humay ug sa mga klase sa humay. Naa ka bay pangutana bahin sa abono, peste, tubig, o pag-ani?'
    else:
        reply_instr = 'Reply in plain English that a smallholder farmer can easily understand. Limit your answer to 3–5 sentences.'
        refusal     = "I'm sorry, I can only help with rice farming and rice varieties. Would you like to ask about fertilizer, pests, water, or harvesting?"

    return f"""You are GeoRice AI, a helpful rice-farming assistant for RiceFlow,
helping smallholder rice farmers in Panabo City, Davao del Norte, Philippines.

REFERENCE — RICE VARIETIES IN OUR DATASET (use these exact facts when asked
about a specific variety; never invent varieties not listed here):

{variety_lines}

LANGUAGE: {lang_label}.
{reply_instr}

WHAT YOU CAN HELP WITH:
1. Rice variety questions — use ONLY the dataset above for variety-specific
   facts (names, ecosystem, maturity days, yield, tolerances). Never invent or
   mention a variety not in the list.
2. General rice (palay) farming practices for Philippine smallholder farmers,
   including: fertilizer types and timing (e.g. 14-14-14, urea/46-0-0, rates per
   hectare), pest and disease management (stem borer, rice bug, brown planthopper,
   blast, sheath blight), water/irrigation management, land preparation,
   transplanting, crop stages, and harvest timing and drying.
3. Practical, field-ready advice a Filipino rice farmer can act on.

STRICT RULES:
1. Stay on RICE (palay) farming only. If asked about OTHER crops (banana, corn,
   coconut, vegetables), market prices, weather forecasts for specific dates,
   politics, sports, news, or anything NOT about rice farming, respond ONLY with:
   "{refusal}"
2. For variety-specific facts, use ONLY the dataset above. Never invent variety
   names, yields, or tolerances that are not listed.
3. Give general rice agronomy advice that is standard for the Philippines; if you
   are unsure of an exact number, give a safe typical range and advise confirming
   with the local DA or PhilRice office.
4. Stay concise and practical. Avoid long essays.
"""


class AIChatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        message  = (request.data.get('message') or '').strip()
        history  = request.data.get('history') or []   # [{role, text}, ...]
        language = (request.data.get('language') or 'en').lower()
        if language not in VALID_LANGS:
            language = 'en'

        if not message:
            return Response(
                {'error': 'Message is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not GEMINI_API_KEY:
            return Response(
                {'error': 'AI service not configured. Add GEMINI_API_KEY to .env'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        system_ctx = _build_system_context(language)

        # Build conversation history for Gemini
        contents = [{
            'role':  'user',
            'parts': [{'text': system_ctx}],
        }, {
            'role':  'model',
            'parts': [{'text': 'Understood. I will help with rice farming and rice varieties, using the dataset for variety facts, and politely decline anything not about rice.'}],
        }]

        for h in history[-6:]:  # keep last 6 exchanges
            role = 'user' if h.get('role') == 'user' else 'model'
            contents.append({
                'role':  role,
                'parts': [{'text': h.get('text', '')}],
            })

        contents.append({
            'role':  'user',
            'parts': [{'text': message}],
        })

        payload = {
            'contents': contents,
            'generationConfig': {
                'temperature':      0.3,
                'maxOutputTokens':  600,
                'thinkingConfig':   {'thinkingBudget': 0},
            },
        }

        try:
            resp = requests.post(
                f'{GEMINI_URL}?key={GEMINI_API_KEY}',
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            data  = resp.json()
            reply = data['candidates'][0]['content']['parts'][0]['text']
            return Response({'reply': reply.strip(), 'language': language})

        except requests.exceptions.Timeout:
            return Response(
                {'error': 'AI service timed out. Please try again.'},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )
        except Exception as e:
            return Response(
                {'error': f'AI error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
