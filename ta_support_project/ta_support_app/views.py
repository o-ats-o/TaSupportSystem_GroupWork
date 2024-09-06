from rest_framework import viewsets, filters
from .models import Data
from .serializers import DataSerializer
from django_filters.rest_framework import DjangoFilterBackend

class DataViewSet(viewsets.ModelViewSet):
    queryset = Data.objects.all()
    serializer_class = DataSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    filterset_fields = ['datetime']
    search_fields = ['group_id']