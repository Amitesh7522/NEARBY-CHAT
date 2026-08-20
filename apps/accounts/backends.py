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

        # Search for user by case-insensitive username, email, or phone number
        clean_username = username.strip()
        clean_digits = ''.join(c for c in clean_username if c.isdigit())
        
        query = Q(username__iexact=clean_username) | Q(email__iexact=clean_username)
        if len(clean_digits) >= 10:
            query |= Q(phone_number__icontains=clean_digits[-10:])

        user = User.objects.filter(query).first()

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
