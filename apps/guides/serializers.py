from rest_framework import serializers
from .models import PlantingGuide, GuideStep
from apps.varieties.serializers import GrowthStageSerializer


class GuideStepSerializer(serializers.ModelSerializer):
    growth_stage = GrowthStageSerializer(read_only=True)

    class Meta:
        model = GuideStep
        fields = '__all__'


class PlantingGuideSerializer(serializers.ModelSerializer):
    steps = GuideStepSerializer(many=True, read_only=True)

    class Meta:
        model = PlantingGuide
        fields = '__all__'


class GuideStepUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuideStep
        fields = ['is_completed', 'completed_at']
