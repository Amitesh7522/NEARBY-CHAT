from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.edit_profile_view, name='edit_profile'),
    path('profile/<str:username>/', views.profile_view, name='user_profile'),
    path('delete/', views.delete_account_view, name='delete_account'),
    
    # OTP REST APIs
    path('api/otp/send/', views.send_otp_api, name='api_send_otp'),
    path('api/otp/verify/', views.verify_otp_api, name='api_verify_otp'),
    path('api/location/update/', views.update_location_api, name='api_update_location'),
]
