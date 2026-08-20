from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('settings/', views.settings_view, name='settings'),
    path('settings/privacy/', views.privacy_settings_view, name='privacy_settings'),
    path('settings/notifications/', views.notification_settings_view, name='notification_settings'),
    path('settings/language/', views.language_settings_view, name='language_settings'),
    path('privacy-policy/', views.privacy_policy_view, name='privacy_policy'),
    path('terms-of-use/', views.terms_of_use_view, name='terms_of_use'),
    path('help-support/', views.help_support_view, name='help_support'),
    path('invite/', views.invite_friends_view, name='invite_friends'),
    path('invite/<str:code>/', views.invite_landing_view, name='invite_landing'),
]
