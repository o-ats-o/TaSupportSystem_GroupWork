from rest_framework import serializers
from .models import Data
from django.utils import timezone

class DataSerializer(serializers.ModelSerializer):
    datetime = serializers.DateTimeField(read_only=True)
    
    class Meta:
        model = Data
        fields = '__all__'
        
    def create(self, validated_data):
        validated_data['datetime'] = timezone.now()
        return super().create(validated_data)