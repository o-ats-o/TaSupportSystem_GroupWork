from django.urls import path
from .views import DataListCreate

urlpatterns = [
    path('data/', DataListCreate.as_view(), name='data-list-create'),
]
