from rest_framework import viewsets, filters
from .models import Data
from .serializers import DataSerializer
from django_filters.rest_framework import DjangoFilterBackend
from .filters import DataFilter
from rest_framework.response import Response
from rest_framework import status

class DataViewSet(viewsets.ModelViewSet):
    queryset = Data.objects.all()
    serializer_class = DataSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    filterset_class = DataFilter
    search_fields = ['group_id']
    
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        if not queryset.exists():
            return Response({"Error": "その時間帯のデータは存在しません"}, status=status.HTTP_404_NOT_FOUND)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)