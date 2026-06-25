from rest_framework import serializers
from .models import Farm


class FarmSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Farm
        fields = '__all__'
        read_only_fields = ['user', 'created_at', 'updated_at']


class AdminFarmSerializer(serializers.ModelSerializer):
    owner_name        = serializers.SerializerMethodField()
    owner_email       = serializers.SerializerMethodField()
    latest_flood_risk = serializers.SerializerMethodField()
    latest_yield_t_ha = serializers.SerializerMethodField()

    def get_owner_name(self, obj):
        first = (obj.user.first_name or '').strip()
        last  = (obj.user.last_name  or '').strip()
        # Collapse legacy duplicates where last_name was stored equal
        # to first_name (e.g. "Frank Frank" -> "Frank").
        if first and last and first.casefold() == last.casefold():
            last = ''
        full = f'{first} {last}'.strip()
        return full or obj.user.username

    def get_owner_email(self, obj):
        return obj.user.email

    def get_latest_flood_risk(self, obj):
        """Flood risk from the most recent environmental scan, if any."""
        scan = obj.scans.order_by('-scanned_at').first()
        return scan.flood_risk if scan else ''

    def get_latest_yield_t_ha(self, obj):
        """Most recent harvest yield in tonnes per hectare, if any."""
        from apps.progress.models import YieldRecord
        record = (
            YieldRecord.objects
                .filter(farm_cycle__farm=obj)
                .order_by('-harvest_date')
                .first()
        )
        return record.yield_per_ha if record else None

    class Meta:
        model  = Farm
        fields = [
            'id', 'name', 'barangay', 'latitude', 'longitude',
            'area_hectares', 'ecosystem', 'elevation_m', 'is_active',
            'created_at', 'owner_name', 'owner_email',
            'latest_flood_risk', 'latest_yield_t_ha',
        ]
