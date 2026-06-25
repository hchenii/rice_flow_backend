from rest_framework import serializers
from .models import EnvironmentalScan


class EnvironmentalScanSerializer(serializers.ModelSerializer):
    class Meta:
        model  = EnvironmentalScan
        fields = '__all__'
