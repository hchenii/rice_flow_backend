from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from apps.farms.models import Farm
from .models import EnvironmentalScan
from .serializers import EnvironmentalScanSerializer
from .services.openmeteo import get_current_weather, get_annual_rainfall, get_elevation
from .services.soilgrids import get_soil_data


class WeatherForecastView(APIView):
    """
    GET /api/environmental/weather/?lat=&lng=
    Returns the current weather + next 3 days of forecast for the dashboard card.
    Pulled live from Open-Meteo (free, no key).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            lat = float(request.query_params.get('lat'))
            lng = float(request.query_params.get('lng'))
        except (TypeError, ValueError):
            return Response({'error': 'lat and lng query params are required'}, status=400)

        try:
            r = requests.get(
                'https://api.open-meteo.com/v1/forecast',
                params={
                    'latitude':  lat,
                    'longitude': lng,
                    'current':   'temperature_2m,weather_code,precipitation,relative_humidity_2m,wind_speed_10m',
                    'hourly':    'temperature_2m,weather_code,precipitation,precipitation_probability',
                    'forecast_days': 2,
                    'timezone':  'Asia/Manila',
                },
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            return Response({'error': f'Open-Meteo unavailable: {e}'}, status=502)

        cur = data.get('current', {})
        h   = data.get('hourly', {})
        hourly_times = h.get('time', [])

        # Find the index of the current hour in the hourly arrays (Manila = UTC+8)
        from datetime import datetime, timedelta
        manila_now = datetime.utcnow() + timedelta(hours=8)
        cur_hr_str = manila_now.strftime('%Y-%m-%dT%H:00')
        start_idx = 0
        for i, t in enumerate(hourly_times):
            if t >= cur_hr_str:
                start_idx = i
                break
        end_idx = min(start_idx + 8, len(hourly_times))

        next_hourly = [
            {
                'time':         hourly_times[i],
                'temp':         h.get('temperature_2m',          [None])[i],
                'weather_code': h.get('weather_code',            [None])[i],
                'rainfall_mm':  h.get('precipitation',           [None])[i],
                'rain_prob':    h.get('precipitation_probability',[None])[i],
            }
            for i in range(start_idx, end_idx)
        ]

        # Rain % for the dashboard card = max precipitation_probability in the next 6 hours
        upcoming_probs = [x.get('rain_prob') for x in next_hourly[:6] if x.get('rain_prob') is not None]
        rain_pct = max(upcoming_probs) if upcoming_probs else 0

        wind_kph_raw = cur.get('wind_speed_10m') or 0

        return Response({
            'current': {
                'temperature':    cur.get('temperature_2m'),
                'weather_code':   cur.get('weather_code'),
                'rainfall_mm':    cur.get('precipitation'),
                'humidity':       cur.get('relative_humidity_2m'),
                'wind_speed_kph': round(wind_kph_raw),
                'wind_speed_ms':  round(wind_kph_raw / 3.6, 1),
                'rain_pct':       round(rain_pct),
            },
            'hourly': next_hourly,
        })

WEATHER_FALLBACK = {
    'avg_temperature': 27.0, 'temp_at_flowering': 27.0,
    'weekly_rainfall_mm': 120.0, 'humidity_pct': 80.0,
    'solar_radiation': 17.0, 'wind_speed_ms': 2.5, 'sunshine_hours': 6.0,
}
SOIL_FALLBACK = {
    'ph': 6.2, 'texture': 'loam', 'organic_matter': 2.5,
    'drainage': 'moderately drained', 'cec': 20.0,
    'nitrogen_ppm': 15.0, 'bulk_density': 1.3,
}


def _safe(fn, *args, fallback=None):
    try:
        return fn(*args)
    except Exception:
        return fallback


class ScanFarmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, farm_id):
        try:
            farm = Farm.objects.get(id=farm_id, user=request.user)
        except Farm.DoesNotExist:
            return Response({'error': 'Farm not found.'}, status=status.HTTP_404_NOT_FOUND)

        lat = float(farm.latitude)
        lon = float(farm.longitude)

        # Run all external API calls in parallel with individual fallbacks
        with ThreadPoolExecutor(max_workers=4) as ex:
            f_weather   = ex.submit(_safe, get_current_weather, lat, lon, fallback=WEATHER_FALLBACK)
            f_annual    = ex.submit(_safe, get_annual_rainfall,  lat, lon, fallback=1800.0)
            f_elevation = ex.submit(_safe, get_elevation,         lat, lon, fallback=10.0)
            f_soil      = ex.submit(_safe, get_soil_data,         lat, lon, fallback=SOIL_FALLBACK)

        weather   = f_weather.result()
        annual    = f_annual.result()
        elevation = f_elevation.result()
        soil      = f_soil.result()

        slope = request.data.get('slope_pct', farm.slope_pct or 1.0)

        flood_risk = 'High' if (
            weather['weekly_rainfall_mm'] > 300 or
            farm.ecosystem == 'rainfed_lowland' and elevation < 50
        ) else 'Low'

        scan = EnvironmentalScan.objects.create(
            farm=farm,
            soil_ph=soil['ph'],
            soil_texture=soil['texture'],
            organic_matter=soil['organic_matter'],
            drainage=soil['drainage'],
            cec=soil['cec'],
            nitrogen_ppm=soil['nitrogen_ppm'],
            bulk_density=soil['bulk_density'],
            avg_temperature=weather['avg_temperature'],
            temp_at_flowering=weather['temp_at_flowering'],
            annual_rainfall_mm=annual,
            seasonal_rainfall_mm=weather['weekly_rainfall_mm'] * 4,
            humidity_pct=weather['humidity_pct'],
            solar_radiation=weather['solar_radiation'],
            wind_speed_ms=weather['wind_speed_ms'],
            sunshine_hours=weather['sunshine_hours'],
            elevation_m=elevation,
            slope_pct=slope,
            flood_risk=flood_risk,
        )

        farm.elevation_m = elevation
        farm.save(update_fields=['elevation_m'])

        return Response(EnvironmentalScanSerializer(scan).data, status=status.HTTP_201_CREATED)


class ScanHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, farm_id):
        scans = EnvironmentalScan.objects.filter(farm__id=farm_id, farm__user=request.user)
        return Response(EnvironmentalScanSerializer(scans, many=True).data)
