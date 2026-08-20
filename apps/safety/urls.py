from django.urls import path
from . import views

app_name = 'safety'

urlpatterns = [
    path('block/<str:username>/', views.block_user_view, name='block_user'),
    path('unblock/<str:username>/', views.unblock_user_view, name='unblock_user'),
    path('blocked-users/', views.blocked_users_list_view, name='blocked_users'),
    path('report/', views.file_report_view, name='file_report'),
]
