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
        return Farm.objects.filter(user=self.request.user)

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
