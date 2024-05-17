from django.shortcuts import render
from rest_framework import generics
from .models import Data
from .serializers import DataSerializer

class DataListCreate(generics.ListCreateAPIView):
    queryset = Data.objects.all()
    serializer_class = DataSerializer