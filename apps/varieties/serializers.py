from rest_framework import serializers
from .models import RiceVariety, GrowthStage, FertilizerSchedule, PestDisease


class RiceVarietySerializer(serializers.ModelSerializer):
    class Meta:
        model = RiceVariety
        fields = '__all__'


class GrowthStageSerializer(serializers.ModelSerializer):
    class Meta:
        model = GrowthStage
        fields = '__all__'


class FertilizerScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = FertilizerSchedule
        fields = '__all__'


class PestDiseaseSerializer(serializers.ModelSerializer):
    resistant_varieties = RiceVarietySerializer(many=True, read_only=True)

    class Meta:
        model = PestDisease
        fields = '__all__'
