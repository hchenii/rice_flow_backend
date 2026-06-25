import os
import time
import concurrent.futures
import requests

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import Avg, Count
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from .serializers import RegisterSerializer, LoginSerializer, UserSerializer

User = get_user_model()


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            return Response(serializer.validated_data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


def _clean_full_name(user):
    """
    Build a display name from first_name/last_name, but collapse the
    legacy duplication where last_name was stored equal to first_name
    (e.g. 'Juan Juan' becomes 'Juan'). Falls back to username.
    """
    first = (user.first_name or '').strip()
    last  = (user.last_name  or '').strip()
    if first and last and first.casefold() == last.casefold():
        return first
    full = f'{first} {last}'.strip()
    return full or user.username


class AdminUserListView(APIView):
    """GET /api/auth/users/ — admin-only list of all users."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        users = User.objects.all().order_by('-date_joined')
        return Response([_user_payload(u) for u in users])

    def post(self, request):
        """Create a new user account (admin-initiated)."""
        return _create_or_update_user(request, instance=None)

    def patch(self, request):
        """
        Legacy: toggle is_active by sending {id, is_active} in the body.
        Kept for the existing toggle buttons; prefer the per-id detail
        endpoint for full edits.
        """
        user_id = request.data.get('id')
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
        if 'is_active' in request.data:
            user.is_active = bool(request.data['is_active'])
        user.save()
        return Response({'id': user.id, 'is_active': user.is_active})


class AdminUserDetailView(APIView):
    """
    GET    /api/auth/users/<id>/ — fetch one user
    PATCH  /api/auth/users/<id>/ — update credentials, role, address
    DELETE /api/auth/users/<id>/ — soft delete (sets is_active=False)
    """
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        try:
            return Response(_user_payload(User.objects.get(pk=pk)))
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    def patch(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
        return _create_or_update_user(request, instance=user)

    def delete(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
        # Safety: don't let an admin lock themselves out.
        if user.pk == request.user.pk:
            return Response(
                {'error': 'You cannot deactivate your own account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.is_active = False
        user.save(update_fields=['is_active'])
        return Response({'id': user.id, 'is_active': False})


# ──────────────────────────────────────────────────────────────────────────
# Helpers used by the admin create/update endpoints
# ──────────────────────────────────────────────────────────────────────────
def _user_payload(u):
    first = (u.first_name or '').strip()
    last  = (u.last_name  or '').strip()
    if first and last and first.casefold() == last.casefold():
        last = ''  # collapse the legacy duplicate

    # Real GPS location comes from the user's active farm pin (Nominatim
    # has already resolved its barangay). Fall back to the registered
    # typed address if the user has not pinned a farm yet.
    active_farm = (
        u.farms.filter(is_active=True).order_by('-created_at').first()
        if u.is_authenticated or True else None
    )
    if active_farm:
        gps_payload = {
            'has_gps':       True,
            'gps_latitude':  float(active_farm.latitude)  if active_farm.latitude  is not None else None,
            'gps_longitude': float(active_farm.longitude) if active_farm.longitude is not None else None,
            'gps_barangay':  active_farm.barangay or '',
            'gps_farm_id':   active_farm.id,
            'gps_farm_name': active_farm.name,
        }
    else:
        gps_payload = {
            'has_gps':       False,
            'gps_latitude':  None,
            'gps_longitude': None,
            'gps_barangay':  '',
            'gps_farm_id':   None,
            'gps_farm_name': '',
        }

    return {
        'id':           u.id,
        'name':         _clean_full_name(u),
        'first_name':   first,
        'last_name':    last,
        'email':        u.email,
        'username':     u.username,
        'phone':        u.phone or '',
        'is_active':    u.is_active,
        'is_staff':     u.is_staff,
        'is_superuser': u.is_superuser,
        'farm_count':   u.farms.count(),
        'date_joined':  u.date_joined.isoformat(),
        'last_login':   u.last_login.isoformat() if u.last_login else None,
        'barangay':     u.barangay or '',
        'municipality': u.municipality or '',
        'province':     u.province or '',
        **gps_payload,
    }


# Whitelist of plain-text fields the admin is allowed to set.
_EDITABLE_FIELDS = (
    'username', 'email', 'first_name', 'last_name',
    'phone', 'barangay', 'municipality', 'province',
)
_ROLES = ('farmer', 'admin', 'superadmin')


def _create_or_update_user(request, instance=None):
    """Shared logic for POST create and PATCH edit."""
    data = request.data or {}
    creating = instance is None
    errors = {}

    # Required fields on create.
    if creating:
        for f in ('username', 'email', 'password'):
            if not (data.get(f) or '').strip():
                errors[f] = f'{f} is required.'

    # Uniqueness on username / email if provided.
    new_username = (data.get('username') or '').strip()
    if new_username:
        qs = User.objects.filter(username__iexact=new_username)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            errors['username'] = 'Username already taken.'

    new_email = (data.get('email') or '').strip()
    if new_email:
        qs = User.objects.filter(email__iexact=new_email)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            errors['email'] = 'Email already registered.'

    # Role validation.
    role = (data.get('role') or '').strip().lower()
    if role and role not in _ROLES:
        errors['role'] = f"role must be one of: {', '.join(_ROLES)}."

    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    user = instance or User()
    for f in _EDITABLE_FIELDS:
        if f in data and data[f] is not None:
            setattr(user, f, str(data[f]).strip())

    # Role → is_staff / is_superuser mapping.
    if role:
        if role == 'farmer':
            user.is_staff = False
            user.is_superuser = False
        elif role == 'admin':
            user.is_staff = True
            user.is_superuser = False
        elif role == 'superadmin':
            user.is_staff = True
            user.is_superuser = True

    # is_active toggle (optional on edit).
    if 'is_active' in data:
        user.is_active = bool(data['is_active'])

    # Password — required on create, optional on edit.
    new_password = (data.get('password') or '').strip()
    if creating and len(new_password) < 8:
        return Response({'password': 'Password must be at least 8 characters.'},
                        status=status.HTTP_400_BAD_REQUEST)
    if new_password:
        if len(new_password) < 8:
            return Response({'password': 'Password must be at least 8 characters.'},
                            status=status.HTTP_400_BAD_REQUEST)
        user.set_password(new_password)

    if creating:
        # Required defaults for new user.
        if not user.municipality:
            user.municipality = 'Panabo City'
        if not user.province:
            user.province = 'Davao del Norte'

    user.save()
    return Response(
        _user_payload(user),
        status=status.HTTP_201_CREATED if creating else status.HTTP_200_OK,
    )


class SystemHealthView(APIView):
    """
    GET /api/auth/system-health/

    Pings every external API + the database in parallel and returns the
    live status of each service. Used by the admin Dashboard's
    "System Health" panel — replaces the previously hardcoded values.

    Each check has a 3-second timeout so the whole endpoint always
    responds within ~3 seconds even when an external service is down.
    """
    permission_classes = [IsAdminUser]
    TIMEOUT = 3

    # Probe URLs that respond quickly. We use Panabo coords so the same
    # cache layer the app uses gets exercised.
    PROBES = [
        {
            'key':   'open_meteo',
            'label': 'Open-Meteo API',
            'url':   'https://api.open-meteo.com/v1/elevation?latitude=7.3086&longitude=125.6839',
        },
        {
            'key':   'soilgrids',
            'label': 'SoilGrids API',
            'url':   'https://rest.isric.org/soilgrids/v2.0/properties/query'
                     '?lon=125.6839&lat=7.3086&property=phh2o&depth=0-5cm&value=mean',
        },
        {
            'key':   'nominatim',
            'label': 'OSM Nominatim',
            'url':   'https://nominatim.openstreetmap.org/reverse'
                     '?lat=7.3086&lon=125.6839&format=json',
        },
    ]

    def _probe_http(self, probe):
        started = time.perf_counter()
        try:
            res = requests.get(
                probe['url'],
                timeout=self.TIMEOUT,
                headers={'User-Agent': 'RiceFlow-Admin/1.0'},
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            ok = 200 <= res.status_code < 400
            return {
                'key':         probe['key'],
                'label':       probe['label'],
                'ok':          ok,
                'status':      'operational' if ok else f'error {res.status_code}',
                'latency_ms':  latency_ms,
            }
        except requests.exceptions.Timeout:
            return {
                'key': probe['key'], 'label': probe['label'],
                'ok': False, 'status': 'timeout',
                'latency_ms': int(self.TIMEOUT * 1000),
            }
        except Exception as e:  # noqa: BLE001
            return {
                'key': probe['key'], 'label': probe['label'],
                'ok': False, 'status': f'unreachable',
                'latency_ms': None, 'error': str(e)[:120],
            }

    def _probe_db(self):
        started = time.perf_counter()
        try:
            with connection.cursor() as c:
                c.execute('SELECT 1')
                c.fetchone()
            return {
                'key': 'database', 'label': 'Supabase database',
                'ok': True, 'status': 'operational',
                'latency_ms': int((time.perf_counter() - started) * 1000),
            }
        except Exception as e:  # noqa: BLE001
            return {
                'key': 'database', 'label': 'Supabase database',
                'ok': False, 'status': 'unreachable',
                'latency_ms': None, 'error': str(e)[:120],
            }

    def _probe_gemini(self):
        """Don't call Gemini (costs quota) — just check the key exists."""
        key = os.getenv('GEMINI_API_KEY', '').strip()
        return {
            'key':   'gemini',
            'label': 'Google Gemini API',
            'ok':    bool(key),
            'status': 'configured' if key else 'no API key',
            'latency_ms': None,
        }

    def get(self, request):
        # Django backend is always healthy if this code is running.
        results = [{
            'key':   'backend',
            'label': 'Django backend',
            'ok':    True,
            'status': 'operational',
            'latency_ms': 0,
        }]

        # Run external probes in parallel for speed.
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futures = [ex.submit(self._probe_http, p) for p in self.PROBES]
            futures.append(ex.submit(self._probe_db))
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        # Gemini check is synchronous and trivial.
        results.append(self._probe_gemini())

        # Preserve a sensible display order matching the dashboard panel.
        order = ['backend', 'database', 'open_meteo', 'soilgrids', 'nominatim', 'gemini']
        results.sort(key=lambda r: order.index(r['key']) if r['key'] in order else 99)

        all_ok = all(r['ok'] for r in results)
        return Response({
            'services': results,
            'all_ok':   all_ok,
            'checked_at': time.time(),
        })


class AdminStatsView(APIView):
    """GET /api/auth/admin-stats/ — dashboard KPIs for the admin panel."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from datetime import timedelta
        from django.utils import timezone
        from django.db.models import Sum, F, FloatField, ExpressionWrapper
        from apps.farms.models import Farm
        from apps.progress.models import YieldRecord, FarmCycle
        from apps.varieties.models import RiceVariety
        from apps.recommendations.models import Recommendation, RecommendationResult

        now           = timezone.now()
        week_ago      = now - timedelta(days=7)
        prev_week_ago = now - timedelta(days=14)
        month_start   = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        total_farms   = Farm.objects.count()
        active_farms  = Farm.objects.filter(is_active=True).count()
        total_users   = User.objects.filter(is_staff=False).count()
        total_cycles  = FarmCycle.objects.count()
        active_cycles = FarmCycle.objects.filter(status='active').count()

        # ── Growth deltas (this week vs last week) ─────────────────────
        new_users_this_week = User.objects.filter(
            is_staff=False, date_joined__gte=week_ago
        ).count()
        new_users_prev_week = User.objects.filter(
            is_staff=False, date_joined__gte=prev_week_ago, date_joined__lt=week_ago
        ).count()
        new_farms_this_week = Farm.objects.filter(created_at__gte=week_ago).count()

        recommendations_this_month = Recommendation.objects.filter(
            created_at__gte=month_start
        ).count()

        # ── Total area under active cultivation ────────────────────────
        total_hectares = (
            Farm.objects.filter(is_active=True)
                .aggregate(total=Sum('area_hectares'))['total']
        ) or 0
        total_hectares = round(float(total_hectares), 2)

        # ── Average yield in tonnes per hectare (proper calc) ──────────
        # Computed in Python via the model's yield_per_ha property because
        # we can't express net_yield_kg / area_harvested_ha / 1000 cleanly
        # as a single SQL Avg without dividing by zero risk.
        yield_records = YieldRecord.objects.exclude(
            area_harvested_ha__isnull=True
        ).exclude(area_harvested_ha=0)
        yp_values     = [r.yield_per_ha for r in yield_records if r.yield_per_ha]
        avg_yield_t   = round(sum(yp_values) / len(yp_values), 2) if yp_values else 0
        total_records = yield_records.count()

        # ── Total harvest tonnage logged across all records ────────────
        total_harvest_kg = (
            YieldRecord.objects.aggregate(total=Sum('net_yield_kg'))['total']
        ) or 0
        total_harvest_t = round(float(total_harvest_kg) / 1000, 2)

        stage_dist = (
            FarmCycle.objects
            .filter(status='active', current_stage__isnull=False)
            .values('current_stage__name')
            .annotate(count=Count('id'))
        )

        # ── Farms grouped by ecosystem (for the donut chart) ───────────
        farms_by_ecosystem = list(
            Farm.objects.filter(is_active=True)
                .values('ecosystem')
                .annotate(count=Count('id'))
        )

        # ── Top location (where most farms are) ────────────────────────
        # We DON'T use the typed `barangay` column here because farmers
        # often enter junk values during registration. Instead, group
        # active farms by their GPS coordinates (rounded to ~1 km) and
        # return the representative lat/lng — the admin dashboard will
        # reverse-geocode it via Nominatim to get the real address.
        from collections import Counter
        buckets = Counter()
        bucket_to_farms = {}
        for f in Farm.objects.filter(
            is_active=True,
            latitude__isnull=False,
            longitude__isnull=False,
        ):
            key = (round(float(f.latitude), 2), round(float(f.longitude), 2))
            buckets[key] += 1
            bucket_to_farms.setdefault(key, []).append(f)
        if buckets:
            (lat, lng), count = buckets.most_common(1)[0]
            sample = bucket_to_farms[(lat, lng)][0]
            top_location = {
                'lat':   float(sample.latitude),
                'lng':   float(sample.longitude),
                'count': count,
            }
        else:
            top_location = None

        # ── Top recommended varieties (top-5 by recommendation count) ──
        top_varieties = list(
            RecommendationResult.objects
                .values('variety__common_name', 'variety__nsic_code',
                        'variety__avg_yield_t_ha', 'variety__ecosystem')
                .annotate(rec_count=Count('id'))
                .order_by('-rec_count')[:5]
        )
        top_varieties = [{
            'common_name':     r['variety__common_name'],
            'nsic_code':       r['variety__nsic_code'],
            'avg_yield_t_ha':  r['variety__avg_yield_t_ha'],
            'ecosystem':       r['variety__ecosystem'],
            'rec_count':       r['rec_count'],
        } for r in top_varieties]

        total_recommendations = Recommendation.objects.count()
        active_varieties      = RiceVariety.objects.filter(is_active=True).count()

        # ── Recent activity feed (last 8 events across the system) ─────
        events = []
        for u in User.objects.filter(is_staff=False).order_by('-date_joined')[:5]:
            events.append({
                'type':     'user_registered',
                'when':     u.date_joined.isoformat(),
                'actor':    _clean_full_name(u),
                'message':  'registered',
            })
        for f in Farm.objects.order_by('-created_at')[:5]:
            events.append({
                'type':     'farm_pinned',
                'when':     f.created_at.isoformat(),
                'actor':    _clean_full_name(f.user),
                'message':  f'pinned farm "{f.name}" in {f.barangay or "—"}',
            })
        for r in (Recommendation.objects.select_related('farm__user')
                                        .order_by('-created_at')[:5]):
            events.append({
                'type':     'recommendation',
                'when':     r.created_at.isoformat(),
                'actor':    _clean_full_name(r.farm.user),
                'message':  f'received a recommendation for "{r.farm.name}"',
            })
        for y in (YieldRecord.objects.select_related('farm_cycle__farm__user')
                                       .order_by('-recorded_at')[:5]):
            farm = y.farm_cycle.farm if y.farm_cycle else None
            user = farm.user if farm else None
            events.append({
                'type':     'yield_logged',
                'when':     y.recorded_at.isoformat(),
                'actor':    _clean_full_name(user) if user else 'Unknown',
                'message':  f'logged a harvest of {round((y.net_yield_kg or 0) / 1000, 2)} t',
            })
        events.sort(key=lambda e: e['when'], reverse=True)
        recent_activity = events[:10]

        return Response({
            'total_farms':                total_farms,
            'active_farms':               active_farms,
            'total_users':                total_users,
            'total_cycles':               total_cycles,
            'active_cycles':              active_cycles,
            'avg_yield_t_ha':             avg_yield_t,
            'yield_records':              total_records,
            'total_harvest_t':            total_harvest_t,
            'total_hectares':             total_hectares,
            'stage_distribution':         list(stage_dist),
            'farms_by_ecosystem':         farms_by_ecosystem,
            'top_varieties':              top_varieties,
            'top_location':               top_location,  # {'lat', 'lng', 'count'} or None
            'total_recommendations':      total_recommendations,
            'recommendations_this_month': recommendations_this_month,
            'active_varieties':           active_varieties,
            'new_users_this_week':        new_users_this_week,
            'new_users_prev_week':        new_users_prev_week,
            'new_farms_this_week':        new_farms_this_week,
            'recent_activity':            recent_activity,
        })
