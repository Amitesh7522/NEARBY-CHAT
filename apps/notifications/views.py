from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Notification, WebPushSubscription

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def notification_list_api(request):
    notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')[:20]
    data = [{
        'id': str(n.id),
        'title': n.title,
        'message': n.message,
        'verb': n.verb,
        'target_type': n.target_type,
        'target_id': n.target_id,
        'is_read': n.is_read,
        'created_at': n.created_at.isoformat(),
    } for n in notifications]
    return Response({'notifications': data})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_read_api(request, notification_id):
    notif = get_object_or_404(Notification, id=notification_id, recipient=request.user)
    notif.is_read = True
    notif.save(update_fields=['is_read'])
    return Response({'success': True})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def push_subscribe_api(request):
    """
    Registers or updates a WebPushSubscription endpoint for the authenticated user.
    """
    endpoint = request.data.get('endpoint')
    p256dh = request.data.get('p256dh', '')
    auth = request.data.get('auth', '')

    if not endpoint:
        return Response({'success': False, 'error': 'Endpoint is required.'}, status=400)

    sub, created = WebPushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            'user': request.user,
            'p256dh': p256dh,
            'auth': auth,
        }
    )
    return Response({'success': True, 'created': created})
