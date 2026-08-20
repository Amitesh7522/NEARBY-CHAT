from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.accounts.models import Profile

User = get_user_model()

class UpdateLastActiveMiddleware:
    """
    Updates the user's last_active and profile last_seen timestamp 
    at most once every 60 seconds to avoid high database write load.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            now = timezone.now()
            # Only update if last_active is older than 60 seconds
            if (now - request.user.last_active).total_seconds() > 60:
                User.objects.filter(id=request.user.id).update(last_active=now)
                Profile.objects.filter(user_id=request.user.id).update(last_seen=now)
        
        response = self.get_response(request)
        return response
