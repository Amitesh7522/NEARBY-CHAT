from django.urls import path
from . import views

app_name = 'private_rooms'

urlpatterns = [
    path('', views.landing_view, name='landing'),
    path('create/', views.create_view, name='create'),
    path('created/<str:secure_token>/', views.created_share_view, name='created_share'),
    path('join/', views.join_code_view, name='join_code'),
    path('invite/<str:secure_token>/', views.invite_landing_view, name='invite_landing'),
    path('invite/<str:secure_token>/join/', views.join_invite_view, name='join_invite'),
    path('room/<uuid:room_id>/', views.room_chat_view, name='chat'),
    path('room/<uuid:room_id>/upload/', views.upload_media_view, name='upload_media'),
    path('room/<uuid:room_id>/delete/', views.delete_room_view, name='delete_room'),
    path('room/<uuid:room_id>/leave/', views.leave_room_view, name='leave_room'),
    path('room/<uuid:room_id>/report/', views.report_room_view, name='report_room'),
    path('media/<uuid:message_id>/', views.serve_media_view, name='serve_media'),
]

