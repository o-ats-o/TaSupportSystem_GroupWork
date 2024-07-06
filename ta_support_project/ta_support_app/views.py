from warnings import filters
from rest_framework import viewsets
from .models import Data
from .serializers import DataSerializer

class DataViewSet(viewsets.ModelViewSet):
    queryset = Data.objects.all()
    serializer_class = DataSerializer
    filter_backends = [filters.SearchFilter]
    serach_fields = ['group_id']