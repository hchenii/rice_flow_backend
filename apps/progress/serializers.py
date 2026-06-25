from rest_framework import serializers
from .models import FarmCycle, ProgressLog, YieldRecord


class FarmCycleSerializer(serializers.ModelSerializer):
    yield_per_ha = serializers.SerializerMethodField()

    class Meta:
        model = FarmCycle
        fields = '__all__'

    def get_yield_per_ha(self, obj):
        yr = getattr(obj, 'yield_record', None)
        return yr.yield_per_ha if yr else None


class ProgressLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProgressLog
        fields = '__all__'


class YieldRecordSerializer(serializers.ModelSerializer):
    yield_per_ha = serializers.ReadOnlyField()

    class Meta:
        model = YieldRecord
        fields = '__all__'
