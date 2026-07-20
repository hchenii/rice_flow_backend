from datetime import timedelta
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from .models import Farm
from .serializers import FarmSerializer, AdminFarmSerializer


class FarmListCreateView(generics.ListCreateAPIView):
    serializer_class   = FarmSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Object-level scoping: a user only ever sees their own farms.
        return Farm.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Idempotency guard: if the same farm (same user + name + coordinates)
        # was created in the last 5 minutes, return it instead of inserting a
        # duplicate. Protects against double-submits / screen remounts in the
        # add-farm flow that otherwise create two identical farms.
        v    = serializer.validated_data
        dupe = Farm.objects.filter(
            user=request.user,
            name=v.get('name'),
            latitude=v.get('latitude'),
            longitude=v.get('longitude'),
            created_at__gte=timezone.now() - timedelta(minutes=5),
        ).first()
        if dupe:
            return Response(FarmSerializer(dupe).data, status=status.HTTP_200_OK)

        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class FarmDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class   = FarmSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Farm.objects.filter(user=self.request.user)


class AdminFarmListView(generics.ListAPIView):
    """GET /api/farms/all/ — admin view of every farm with owner info."""
    serializer_class   = AdminFarmSerializer
    permission_classes = [IsAdminUser]
    queryset           = Farm.objects.select_related('user').all()
    pagination_class   = None


class AdminFarmDeleteView(APIView):
    """DELETE /api/farms/admin/<pk>/ — admin hard-delete of any farm."""
    permission_classes = [IsAdminUser]

    def delete(self, request, pk):
        try:
            farm = Farm.objects.get(pk=pk)
        except Farm.DoesNotExist:
            return Response({'error': 'Farm not found.'}, status=status.HTTP_404_NOT_FOUND)
        farm.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminFarmCleanupView(APIView):
    """POST /api/farms/cleanup/ — keep only the newest farm per user, delete the rest."""
    permission_classes = [IsAdminUser]

    def post(self, request):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        deleted_total = 0
        for user in User.objects.all():
            farms = list(Farm.objects.filter(user=user).order_by('-created_at'))
            if len(farms) > 1:
                to_delete = farms[1:]  # keep farms[0] (newest)
                ids = [f.id for f in to_delete]
                Farm.objects.filter(id__in=ids).delete()
                deleted_total += len(ids)
        return Response({'deleted': deleted_total})
