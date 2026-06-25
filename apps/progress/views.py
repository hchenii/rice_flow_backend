from rest_framework import status
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import FarmCycle, ProgressLog, YieldRecord
from .serializers import FarmCycleSerializer, ProgressLogSerializer, YieldRecordSerializer


def _clean_full_name(u):
    """Same dedupe used elsewhere — collapses 'Frank Frank' -> 'Frank'."""
    first = (u.first_name or '').strip()
    last  = (u.last_name  or '').strip()
    if first and last and first.casefold() == last.casefold():
        last = ''
    full = f'{first} {last}'.strip()
    return full or u.username


class AdminFarmCycleListView(APIView):
    """
    GET    /api/progress/admin/cycles/        — list every cycle across all users
    DELETE /api/progress/admin/cycles/<id>/   — handled by AdminFarmCycleDetailView
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        cycles = (
            FarmCycle.objects
                .select_related('farm__user', 'variety', 'current_stage')
                .order_by('-planting_date', '-id')
        )

        # Optional filters straight from query string.
        status_filter = request.query_params.get('status')
        if status_filter in ('active', 'completed', 'abandoned'):
            cycles = cycles.filter(status=status_filter)

        owner_id = request.query_params.get('owner_id')
        if owner_id:
            cycles = cycles.filter(farm__user_id=owner_id)

        data = []
        for c in cycles:
            yr   = getattr(c, 'yield_record', None)
            farm = c.farm
            user = farm.user
            data.append({
                'id':                    c.id,
                'farm_id':               farm.id,
                'farm_name':             farm.name,
                'owner_id':              user.id,
                'owner_name':            _clean_full_name(user),
                'owner_email':           user.email,
                'barangay':              farm.barangay or '',
                'latitude':              float(farm.latitude),
                'longitude':             float(farm.longitude),
                'ecosystem':             farm.ecosystem,
                'area_ha':               float(c.area_planted_ha or farm.area_hectares or 0),
                'variety_id':            c.variety_id,
                'variety':               c.variety.common_name if c.variety else None,
                'nsic_code':             c.variety.nsic_code   if c.variety else None,
                'season':                c.season,
                'year':                  c.year,
                'planting_date':         c.planting_date.isoformat()         if c.planting_date         else None,
                'expected_harvest_date': c.expected_harvest_date.isoformat() if c.expected_harvest_date else None,
                'actual_harvest_date':   c.actual_harvest_date.isoformat()   if c.actual_harvest_date   else None,
                'current_stage':         c.current_stage.name if c.current_stage else None,
                'stage_no':              c.current_stage.stage_no if c.current_stage else None,
                'status':                c.status,
                'yield_t_ha':            yr.yield_per_ha if yr else None,
                'created_at':            c.created_at.isoformat(),
            })
        return Response(data)


class AdminFarmCycleDetailView(APIView):
    permission_classes = [IsAdminUser]

    def delete(self, request, pk):
        try:
            cycle = FarmCycle.objects.get(pk=pk)
        except FarmCycle.DoesNotExist:
            return Response({'error': 'Farm cycle not found.'},
                            status=status.HTTP_404_NOT_FOUND)
        cycle.delete()
        return Response({'id': pk, 'deleted': True})


class FarmCycleListCreateView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FarmCycleSerializer

    def get_queryset(self):
        qs = FarmCycle.objects.filter(farm__user=self.request.user)
        farm_id = self.request.query_params.get('farm_id')
        if farm_id:
            qs = qs.filter(farm_id=farm_id)
        return qs


class FarmCycleDetailView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FarmCycleSerializer

    def get_queryset(self):
        return FarmCycle.objects.filter(farm__user=self.request.user)


class ProgressLogListCreateView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProgressLogSerializer

    def get_queryset(self):
        qs = ProgressLog.objects.filter(farm_cycle__farm__user=self.request.user)
        cycle_id = self.request.query_params.get('cycle_id')
        if cycle_id:
            qs = qs.filter(farm_cycle_id=cycle_id)
        return qs


class ProgressLogDetailView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProgressLogSerializer

    def get_queryset(self):
        return ProgressLog.objects.filter(farm_cycle__farm__user=self.request.user)


class YieldRecordView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_cycle(self, cycle_id, user):
        try:
            return FarmCycle.objects.get(pk=cycle_id, farm__user=user)
        except FarmCycle.DoesNotExist:
            return None

    def get(self, request, cycle_id):
        cycle = self._get_cycle(cycle_id, request.user)
        if not cycle:
            return Response({'detail': 'Farm cycle not found.'}, status=404)
        yr = getattr(cycle, 'yield_record', None)
        if not yr:
            return Response({'detail': 'No yield record yet.'}, status=404)
        return Response(YieldRecordSerializer(yr).data)

    def post(self, request, cycle_id):
        cycle = self._get_cycle(cycle_id, request.user)
        if not cycle:
            return Response({'detail': 'Farm cycle not found.'}, status=404)
        if hasattr(cycle, 'yield_record'):
            return Response({'detail': 'Yield record already exists. Use PATCH to update.'}, status=400)
        data = {**request.data, 'farm_cycle': cycle.id}
        serializer = YieldRecordSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def patch(self, request, cycle_id):
        cycle = self._get_cycle(cycle_id, request.user)
        if not cycle:
            return Response({'detail': 'Farm cycle not found.'}, status=404)
        yr = getattr(cycle, 'yield_record', None)
        if not yr:
            return Response({'detail': 'No yield record to update.'}, status=404)
        serializer = YieldRecordSerializer(yr, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
