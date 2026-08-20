from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('api/', views.notification_list_api, name='api_list'),
    path('api/<uuid:notification_id>/read/', views.mark_read_api, name='api_mark_read'),
    path('push-subscribe/', views.push_subscribe_api, name='push_subscribe'),
]
