from django_filters import rest_framework as filters
from .models import Data

class DataFilter(filters.FilterSet):
    datetime = filters.IsoDateTimeFromToRangeFilter(field_name='datetime')

    class Meta:
        model = Data
        fields = ['datetime']