import csv
import io

from rest_framework import status
from rest_framework.generics import (
    ListAPIView, RetrieveAPIView,
    ListCreateAPIView, RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from .models import RiceVariety, GrowthStage, FertilizerSchedule, PestDisease
from .serializers import (
    RiceVarietySerializer, GrowthStageSerializer,
    FertilizerScheduleSerializer, PestDiseaseSerializer,
)


class _ReadAnyWriteAdmin:
    """Allow any authenticated user to GET, require admin for write methods."""
    def get_permissions(self):
        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            return [IsAuthenticated()]
        return [IsAdminUser()]


class RiceVarietyListView(_ReadAnyWriteAdmin, ListCreateAPIView):
    """
    GET  → list varieties. Admin sees all (active + inactive);
           regular users see only active ones for use in the mobile app.
    POST → create a new variety (admin only).
    """
    serializer_class = RiceVarietySerializer

    def get_queryset(self):
        qs = RiceVariety.objects.all()
        # Mobile app only needs active varieties; admin asks for ?all=1
        # to see inactive entries too.
        if self.request.query_params.get('all') == '1' and self.request.user.is_staff:
            return qs
        return qs.filter(is_active=True)


class VarietyImportCSVView(APIView):
    """
    POST /api/varieties/import-csv/  (admin only · multipart/form-data, file=CSV)

    Imports rice varieties from a CSV file. The file's first row MUST be a
    header row. Required columns: nsic_code, common_name, ecosystem,
    maturity_days, avg_yield_t_ha. Optional: variety_id, season,
    max_yield_t_ha, submergence_tolerance, drought_tolerance,
    salinity_tolerance, optimal_temp_min, optimal_temp_max,
    optimal_rainfall_min, notes, year_released.

    Behaviour:
      - Non-CSV uploads (PDF, image, etc.) → 400 with a clear message.
      - Each row is validated; valid rows are inserted or updated by
        nsic_code; invalid rows are reported with their line number.
      - Response: { created, updated, skipped, errors }
    """
    permission_classes = [IsAdminUser]
    parser_classes     = [MultiPartParser]

    REQUIRED = ['nsic_code', 'common_name', 'ecosystem',
                'maturity_days', 'avg_yield_t_ha']
    ECOSYSTEMS  = {'irrigated_lowland', 'rainfed_lowland', 'upland'}
    TOLERANCES  = {'low', 'moderate', 'high'}

    def post(self, request):
        upload = request.FILES.get('file')
        if not upload:
            return Response(
                {'error': 'No file uploaded. Field name must be "file".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── 1. File-type guard ────────────────────────────────────────
        name        = (upload.name or '').lower()
        content_typ = (upload.content_type or '').lower()
        ext_ok      = name.endswith('.csv')
        mime_ok     = content_typ in ('text/csv', 'application/csv',
                                      'application/vnd.ms-excel',
                                      'text/plain', '')
        if not ext_ok:
            ext = name.rsplit('.', 1)[-1].upper() if '.' in name else 'unknown'
            return Response({
                'error': f'Only CSV files are accepted. You uploaded a {ext} file.',
            }, status=status.HTTP_400_BAD_REQUEST)
        if not mime_ok:
            return Response({
                'error': f'Unexpected file type "{content_typ}". '
                         'Please save your spreadsheet as CSV first.',
            }, status=status.HTTP_400_BAD_REQUEST)

        # ── 2. Decode + parse ─────────────────────────────────────────
        try:
            decoded = upload.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            return Response({
                'error': 'CSV must be UTF-8 encoded. Re-save the file as '
                         '"CSV UTF-8" from Excel or Google Sheets.',
            }, status=status.HTTP_400_BAD_REQUEST)

        reader  = csv.DictReader(io.StringIO(decoded))
        headers = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c for c in self.REQUIRED if c not in headers]
        if missing:
            return Response({
                'error': 'Missing required column(s): ' + ', '.join(missing),
                'expected_columns': self.REQUIRED,
            }, status=status.HTTP_400_BAD_REQUEST)

        # ── 3. Row-by-row import ──────────────────────────────────────
        created, updated, skipped = 0, 0, 0
        errors = []

        for line_no, row in enumerate(reader, start=2):  # 1 = header
            cleaned, row_errors = self._validate_row(row)
            if row_errors:
                errors.append({'line': line_no, 'errors': row_errors})
                skipped += 1
                continue

            nsic = cleaned['nsic_code']
            try:
                existing = RiceVariety.objects.filter(nsic_code__iexact=nsic).first()
                if existing:
                    for k, v in cleaned.items():
                        setattr(existing, k, v)
                    existing.is_active = True
                    existing.save()
                    updated += 1
                else:
                    # variety_id is unique and required at the DB level; auto-
                    # fill it from the NSIC code when the CSV omits it.
                    cleaned.setdefault('variety_id', cleaned['nsic_code'])
                    RiceVariety.objects.create(**cleaned)
                    created += 1
            except Exception as e:  # noqa: BLE001
                errors.append({'line': line_no, 'errors': [str(e)[:160]]})
                skipped += 1

        return Response({
            'created':  created,
            'updated':  updated,
            'skipped':  skipped,
            'errors':   errors,
            'message':  f'Imported {created} new variet{"y" if created == 1 else "ies"}, '
                        f'updated {updated}, skipped {skipped}.',
        }, status=status.HTTP_200_OK)

    # ── helpers ────────────────────────────────────────────────────────
    def _validate_row(self, row):
        errors  = []
        cleaned = {}

        for k, v in row.items():
            if v is None:
                continue
            v = v.strip()
            if k == 'nsic_code':
                if not v:
                    errors.append('nsic_code is empty')
                cleaned['nsic_code'] = v
            elif k == 'variety_id':
                if v:
                    cleaned['variety_id'] = v
            elif k == 'common_name':
                if not v:
                    errors.append('common_name is empty')
                cleaned['common_name'] = v
            elif k == 'ecosystem':
                key = v.lower().replace(' ', '_')
                if key not in self.ECOSYSTEMS:
                    errors.append(
                        f'ecosystem "{v}" must be one of: '
                        + ', '.join(sorted(self.ECOSYSTEMS))
                    )
                else:
                    cleaned['ecosystem'] = key
            elif k == 'maturity_days':
                cleaned['maturity_days'] = self._to_int(v, errors, 'maturity_days')
            elif k == 'avg_yield_t_ha':
                cleaned['avg_yield_t_ha'] = self._to_float(v, errors, 'avg_yield_t_ha')
            elif k == 'max_yield_t_ha':
                cleaned['max_yield_t_ha'] = self._to_float(v, errors, 'max_yield_t_ha')
            elif k in ('submergence_tolerance', 'drought_tolerance', 'salinity_tolerance'):
                if v and v.lower() not in self.TOLERANCES:
                    errors.append(
                        f'{k} "{v}" must be one of: '
                        + ', '.join(sorted(self.TOLERANCES))
                    )
                elif v:
                    cleaned[k] = v.lower()
            elif k in ('optimal_temp_min', 'optimal_temp_max'):
                if v:
                    cleaned[k] = self._to_float(v, errors, k)
            elif k == 'optimal_rainfall_min':
                if v:
                    cleaned[k] = self._to_int(v, errors, k)
            elif k == 'year_released':
                if v:
                    cleaned[k] = self._to_int(v, errors, k)
            elif k in ('season', 'grain_type', 'pagasa_climate_types',
                       'notes', 'pest_resistance', 'disease_resistance'):
                cleaned[k] = v
            # any other unknown column → silently ignored

        # Final required-field check (in case a value parsed to None).
        for req in self.REQUIRED:
            if cleaned.get(req) in (None, ''):
                errors.append(f'{req} is missing')

        return cleaned, errors

    @staticmethod
    def _to_int(v, errors, field):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            errors.append(f'{field} "{v}" must be a whole number')
            return None

    @staticmethod
    def _to_float(v, errors, field):
        try:
            return float(v)
        except (TypeError, ValueError):
            errors.append(f'{field} "{v}" must be a number')
            return None


class RiceVarietyDetailView(_ReadAnyWriteAdmin, RetrieveUpdateDestroyAPIView):
    """
    GET    → retrieve one variety
    PUT    → full update (admin only)
    PATCH  → partial update (admin only)
    DELETE → soft delete by setting is_active=False (admin only)
             so historical recommendations remain intact.
    """
    serializer_class = RiceVarietySerializer
    queryset = RiceVariety.objects.all()

    def perform_destroy(self, instance):
        # Soft delete to preserve referential integrity with historical
        # RecommendationResult rows that point at this variety.
        instance.is_active = False
        instance.save(update_fields=['is_active'])


class GrowthStageListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = GrowthStageSerializer
    queryset = GrowthStage.objects.all()


class FertilizerScheduleListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FertilizerScheduleSerializer
    queryset = FertilizerSchedule.objects.all()


class PestDiseaseListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PestDiseaseSerializer

    def get_queryset(self):
        qs = PestDisease.objects.all()
        type_filter = self.request.query_params.get('type')
        if type_filter in ('pest', 'disease'):
            qs = qs.filter(type=type_filter)
        return qs
