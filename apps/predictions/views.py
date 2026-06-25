from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status

from .models import YieldPredictionModel
from .serializers import YieldPredictionModelSerializer
from .services import train_all_models, predict_yield


class ModelComparisonView(APIView):
    """GET /api/predictions/models/ — list all trained model results."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        models = YieldPredictionModel.objects.all()
        return Response(YieldPredictionModelSerializer(models, many=True).data)


class TrainModelsView(APIView):
    """POST /api/predictions/train/ — retrain all 3 models (admin only)."""
    permission_classes = [IsAdminUser]

    def post(self, request):
        results = train_all_models()

        # Clear old records, save new ones
        YieldPredictionModel.objects.all().delete()
        for r in results:
            YieldPredictionModel.objects.create(**r)

        models = YieldPredictionModel.objects.all()
        return Response({
            'message': 'Models trained successfully.',
            'results': YieldPredictionModelSerializer(models, many=True).data,
        })


class PredictYieldView(APIView):
    """POST /api/predictions/predict/ — predict yield for a farm scan."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        features = request.data
        result   = predict_yield(features)
        return Response(result, status=status.HTTP_200_OK)
