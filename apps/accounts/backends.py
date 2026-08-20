"""
Authentication Backends for Nearby Chat.
Supports authenticating with either username or email address.
"""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

class EmailOrUsernameModelBackend(ModelBackend):
    """
    Allows authentication via username or email.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get('email')
        
        if not username or not password:
            return None

        # Search for user by case-insensitive username or email
        user = User.objects.filter(
            Q(username__iexact=username) | Q(email__iexact=username)
        ).first()

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
