from rest_framework import serializers
from .models import YieldPredictionModel


class YieldPredictionModelSerializer(serializers.ModelSerializer):
    model_type_display = serializers.CharField(
        source='get_model_type_display', read_only=True)

    class Meta:
        model  = YieldPredictionModel
        fields = [
            'id', 'model_type', 'model_type_display',
            'r2_score', 'mae', 'rmse',
            'training_samples', 'is_active',
            'trained_at', 'notes',
        ]
