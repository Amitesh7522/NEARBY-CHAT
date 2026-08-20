from django.urls import path
from . import views

app_name = 'rooms'

urlpatterns = [
    path('', views.room_list_view, name='list'),
    path('create/', views.room_create_view, name='create'),
    path('<uuid:room_id>/', views.room_detail_view, name='detail'),
    path('<uuid:room_id>/join/', views.room_join_view, name='join'),
    path('<uuid:room_id>/leave/', views.room_leave_view, name='leave'),
]
