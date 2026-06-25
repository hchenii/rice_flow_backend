from datetime import date, timedelta

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status
from apps.farms.models import Farm
from apps.environmental.models import EnvironmentalScan
from apps.varieties.models import RiceVariety, GrowthStage
from apps.progress.models import FarmCycle
from .models import ClusterModel, Recommendation, RecommendationResult, SuitabilityRuleSet
from .scoring import calculate_rsi, default_rules_payload
from .clustering import train_all_models, predict_cluster
from .serializers import (
    RecommendationSerializer, ClusterModelSerializer, SuitabilityRuleSetSerializer
)


def ensure_active_cycle_for_recommendation(recommendation):
    """
    Given a Recommendation that already has its top-3 RecommendationResult
    rows saved, create (or return the existing) active FarmCycle for the
    same farm using the rank-1 variety. Idempotent — if an active cycle
    already exists for the farm, returns it unchanged.

    Defaults:
      season = 'wet' if month is May–Oct, else 'dry'
      year = today's year
      planting_date = today
      expected_harvest_date = today + variety.maturity_days
      current_stage = lowest stage_no in GrowthStage (Land Prep / Seedling)
      status = 'active'
      area_planted_ha = farm.area_hectares
    """
    farm = recommendation.farm

    # Skip if this farm already has an active cycle.
    existing = farm.farm_cycles.filter(status='active').first()
    if existing:
        return existing, False

    top = recommendation.results.order_by('rank').first()
    variety = top.variety if top else None
    today   = date.today()
    season  = 'wet' if 5 <= today.month <= 10 else 'dry'

    expected_harvest = None
    if variety and variety.maturity_days:
        expected_harvest = today + timedelta(days=int(variety.maturity_days))

    first_stage = GrowthStage.objects.order_by('stage_no').first()

    cycle = FarmCycle.objects.create(
        farm                  = farm,
        variety               = variety,
        season                = season,
        year                  = today.year,
        planting_date         = today,
        expected_harvest_date = expected_harvest,
        current_stage         = first_stage,
        status                = 'active',
        area_planted_ha       = float(farm.area_hectares) if farm.area_hectares else None,
    )
    return cycle, True


class SuitabilityRulesView(APIView):
    """
    GET  /api/recommendations/rules/  → current active rule set
    PUT  /api/recommendations/rules/  → admin-only update of FAO ranges + WLC weights
    """
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated()]
        return [IsAdminUser()]

    def get(self, request):
        rs = SuitabilityRuleSet.objects.first()
        if not rs:
            # Should not happen because of seed migration, but be safe.
            return Response({
                'payload':         default_rules_payload(),
                'updated_at':      None,
                'updated_by_name': None,
                'source':          'fallback',
            })
        data = SuitabilityRuleSetSerializer(rs).data
        data['source'] = 'database'
        return Response(data)

    def put(self, request):
        rs = SuitabilityRuleSet.objects.first()
        serializer = SuitabilityRuleSetSerializer(rs, data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        rs = serializer.save(updated_by=request.user)
        out = SuitabilityRuleSetSerializer(rs).data
        out['source'] = 'database'
        return Response(out, status=status.HTTP_200_OK)


class GenerateRecommendationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, scan_id):
        try:
            scan = EnvironmentalScan.objects.select_related('farm').get(
                id=scan_id, farm__user=request.user
            )
        except EnvironmentalScan.DoesNotExist:
            return Response({'error': 'Scan not found.'}, status=status.HTTP_404_NOT_FOUND)

        farm      = scan.farm
        ecosystem = farm.ecosystem

        active_model = ClusterModel.objects.filter(is_active=True).first()
        model_name   = active_model.name if active_model else 'kmeans'

        varieties = RiceVariety.objects.filter(is_active=True)

        results = []
        for variety in varieties:
            rsi_data = calculate_rsi(variety, scan, ecosystem)
            v_cluster = predict_cluster(variety, model_name) if active_model else 0
            results.append({
                'variety':         variety,
                'rsi_score':       rsi_data['rsi_score'],
                'suitability_class': rsi_data['suitability_class'],
                'factor_scores':   rsi_data['factor_scores'],
                'variety_cluster': v_cluster,
            })

        results.sort(key=lambda x: x['rsi_score'], reverse=True)
        top3 = results[:3]

        rec = Recommendation.objects.create(
            farm=farm,
            scan=scan,
            cluster_model=active_model,
            farm_cluster=0,
        )

        for i, r in enumerate(top3, 1):
            RecommendationResult.objects.create(
                recommendation=rec,
                variety=r['variety'],
                rank=i,
                rsi_score=r['rsi_score'],
                suitability_class=r['suitability_class'],
                variety_cluster=r['variety_cluster'],
                factor_scores=r['factor_scores'],
            )

        # Auto-create an active FarmCycle so the admin's Farm Cycle
        # Monitoring page reflects the new recommendation immediately.
        # Idempotent: if the farm already has an active cycle, nothing happens.
        ensure_active_cycle_for_recommendation(rec)

        return Response(RecommendationSerializer(rec).data, status=status.HTTP_201_CREATED)


class TrainModelsView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        varieties = list(RiceVariety.objects.filter(is_active=True))
        if len(varieties) < 4:
            return Response({'error': 'Need at least 4 varieties to cluster.'}, status=400)

        results, _ = train_all_models(varieties)

        saved = []
        for name, res in results.items():
            cm, _ = ClusterModel.objects.update_or_create(
                name=name,
                defaults={
                    'training_time_ms': res['training_time_ms'],
                    'silhouette_score': res['silhouette'],
                    'davies_bouldin':   res['davies_bouldin'],
                    'n_clusters':       res['n_clusters'],
                    'is_active':        False,
                }
            )
            saved.append(ClusterModelSerializer(cm).data)

        return Response({'models': saved, 'message': 'Training complete. Select the best model in admin.'})


class SetActiveModelView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, model_name):
        try:
            cm = ClusterModel.objects.get(name=model_name)
            cm.is_active = True
            cm.save()
            return Response({'message': f'{cm.get_name_display()} is now active.'})
        except ClusterModel.DoesNotExist:
            return Response({'error': 'Model not found.'}, status=404)


class RecommendationHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, farm_id):
        recs = Recommendation.objects.filter(farm__id=farm_id, farm__user=request.user)
        return Response(RecommendationSerializer(recs, many=True).data)
