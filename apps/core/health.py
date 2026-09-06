import os
from django.http import JsonResponse
from django.db import connection
from django.core.cache import cache
from django.utils import timezone

def liveness_check_view(request):
    """
    Minimal public liveness probe.
    Returns HTTP 200 without disclosing internal infrastructure or subsystem details.
    """
    return JsonResponse({'status': 'ok'}, status=200)


def readiness_check_view(request):
    """
    Readiness & dependency probe for container orchestrators (Render, Railway, Kubernetes, AWS ALB).
    Validates database and cache availability without leaking sensitive stack traces or connection strings.
    """
    db_ok = False
    cache_ok = False

    # 1. Test Database
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        db_ok = False

    # 2. Test Cache
    try:
        cache.set('nc_ready_probe', 1, 5)
        cache_ok = (cache.get('nc_ready_probe') == 1)
    except Exception:
        cache_ok = False

    is_ready = db_ok and cache_ok
    status_code = 200 if is_ready else 503

    # Check if privileged internal inspect request
    auth_header = request.headers.get('X-Health-Key', '')
    expected_key = os.getenv('HEALTH_CHECK_SECRET', '')
    is_staff = getattr(request, 'user', None) and getattr(request.user, 'is_staff', False)

    if (expected_key and auth_header == expected_key) or is_staff:
        # Provide detailed internal diagnostics for authorized staff / monitoring systems
        return JsonResponse({
            'status': 'ready' if is_ready else 'degraded',
            'timestamp': timezone.now().isoformat(),
            'components': {
                'database': 'healthy' if db_ok else 'unhealthy',
                'cache': 'healthy' if cache_ok else 'unhealthy',
            }
        }, status=status_code)

    # Standard public/orchestrator probe response
    return JsonResponse({
        'status': 'ready' if is_ready else 'degraded'
    }, status=status_code)
