from django.urls import path
from . import views

app_name = 'matching'

urlpatterns = [
    path('', views.matching_radar_view, name='radar'),
    path('radar/', views.matching_radar_view, name='radar_alias'),
]
