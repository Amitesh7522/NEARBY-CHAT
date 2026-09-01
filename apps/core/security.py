"""
Core Security Utilities for NearbyChat:
Image EXIF/GPS Metadata Sanitization, File Upload Security Validation,
and WebSocket Origin Verification.
"""
import io
import os
import re
import uuid
import mimetypes
from urllib.parse import urlparse
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from PIL import Image, ImageOps

# Forbidden dangerous executable/script extensions across the entire platform
DISALLOWED_EXTENSIONS = {
    '.exe', '.bat', '.cmd', '.sh', '.bash', '.vbs', '.js', '.mjs',
    '.dll', '.msi', '.scr', '.pif', '.com', '.jar', '.apk', '.iso',
    '.bin', '.py', '.php', '.asp', '.aspx', '.jsp', '.cgi', '.pl',
    '.html', '.htm', '.xhtml', '.svg', '.hta', '.wsf', '.reg'
}

ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}


def sanitize_and_strip_image_exif(image_file, max_dimension=1600, max_size_bytes=10 * 1024 * 1024):
    """
    Sanitizes uploaded user images (avatars, attachments) across the application:
    - Verifies file size limit.
    - Strips all EXIF / GPS / device metadata.
    - Transposes orientation to prevent sideways images.
    - Optionally caps maximum dimension to prevent memory exhaustion.
    - Re-encodes cleanly.
    """
    if not image_file:
        return None

    raw_name = getattr(image_file, 'name', 'upload.jpg')
    _, ext = os.path.splitext(raw_name)
    ext = ext.lower().strip()

    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(f"Invalid image extension '{ext}'. Allowed: JPG, PNG, WEBP, GIF.")

    file_size = getattr(image_file, 'size', 0)
    if file_size > max_size_bytes:
        raise ValidationError(f"Image exceeds the maximum allowed limit of {max_size_bytes // (1024 * 1024)} MB.")

    try:
        image_bytes = image_file.read()
        image_file.seek(0)
        img = Image.open(io.BytesIO(image_bytes))

        # Rotate according to EXIF orientation before stripping
        img = ImageOps.exif_transpose(img)

        # Scale down if exceeds max_dimension
        if img.width > max_dimension or img.height > max_dimension:
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

        out_io = io.BytesIO()
        fmt = img.format if img.format in ('JPEG', 'PNG', 'WEBP', 'GIF') else ('JPEG' if ext in ('.jpg', '.jpeg') else 'PNG')

        if fmt == 'JPEG':
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            img.save(out_io, format='JPEG', quality=90, optimize=True)
            out_ext = '.jpg'
        elif fmt == 'PNG':
            img.save(out_io, format='PNG', optimize=True)
            out_ext = '.png'
        elif fmt == 'WEBP':
            img.save(out_io, format='WEBP', quality=90)
            out_ext = '.webp'
        elif fmt == 'GIF':
            img.save(out_io, format='GIF')
            out_ext = '.gif'
        else:
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            img.save(out_io, format='JPEG', quality=90)
            out_ext = '.jpg'

        sanitized_bytes = out_io.getvalue()
        storage_name = f"{uuid.uuid4().hex}{out_ext}"
        return ContentFile(sanitized_bytes, name=storage_name)
    except Exception as e:
        # If not a valid image format
        raise ValidationError(f"Unable to process image file: {str(e)}")


def validate_websocket_origin(scope):
    """
    Validates WebSocket Origin header against ALLOWED_HOSTS to prevent CSWSH attacks.
    """
    headers = dict(scope.get('headers', []))
    origin_bytes = headers.get(b'origin')
    if not origin_bytes:
        # Same-origin WebSocket or non-browser client
        return True

    origin = origin_bytes.decode('utf-8', errors='ignore')
    parsed = urlparse(origin)
    origin_host = (parsed.hostname or parsed.netloc.split(':')[0] or '').lower()

    allowed = [h.lower() for h in getattr(settings, 'ALLOWED_HOSTS', [])]

    # Standard check: origin matches allowed hosts
    if origin_host in allowed or origin_host in ('localhost', '127.0.0.1', 'testserver'):
        return True

    # If ALLOWED_HOSTS has wildcard, only allow local hosts or testserver
    if '*' in allowed and origin_host in ('localhost', '127.0.0.1', 'testserver', ''):
        return True

    return False
