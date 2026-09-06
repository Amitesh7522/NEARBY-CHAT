"""
Security and Performance Middleware for NearbyChat.
Applies HTTP security headers (CSP, Permissions-Policy, Referrer-Policy, X-Content-Type-Options).
"""

class SecurityHeadersMiddleware:
    """
    Adds production security headers to HTTP responses.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Content-Security-Policy
        if 'Content-Security-Policy' not in response:
            csp_directives = [
                "default-src 'self'",
                "script-src 'self' 'unsafe-inline'",
                "style-src 'self' 'unsafe-inline'",
                "font-src 'self' data:",
                "connect-src 'self' ws: wss:",
                "img-src 'self' data: blob:",
                "media-src 'self' blob: data:",
                "worker-src 'self' blob:",
                "object-src 'none'",
                "base-uri 'self'",
                "form-action 'self'",
                "frame-ancestors 'none'",
            ]
            response['Content-Security-Policy'] = "; ".join(csp_directives)

        # Permissions-Policy
        if 'Permissions-Policy' not in response:
            response['Permissions-Policy'] = "camera=(), microphone=(self), geolocation=(self)"

        # Referrer-Policy
        if 'Referrer-Policy' not in response:
            response['Referrer-Policy'] = "strict-origin-when-cross-origin"

        # X-Content-Type-Options
        if 'X-Content-Type-Options' not in response:
            response['X-Content-Type-Options'] = "nosniff"

        return response
