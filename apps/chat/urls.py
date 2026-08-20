from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.conversation_list_view, name='list'),
    path('quick-connect/', views.quick_connect_view, name='quick_connect'),
    path('with/<str:username>/', views.start_direct_chat_view, name='start_direct'),
    path('<uuid:conversation_id>/', views.conversation_detail_view, name='detail'),
    path('rate/', views.submit_rating_view, name='submit_rating'),
    path('api/<uuid:conversation_id>/messages/', views.messages_api, name='api_messages'),
]
