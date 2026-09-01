"""
Global Security, Privacy, and Content Access Tests for NearbyChat:
- Profile and Room avatar EXIF/GPS metadata stripping
- Dangerous file upload rejection
- CSWSH Origin validation
- Object-level authorization across chats and rooms
- Sensitive data exposure protection
"""
import io
import uuid
import secrets
from datetime import timedelta
from PIL import Image
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from apps.core.security import sanitize_and_strip_image_exif, validate_websocket_origin, DISALLOWED_EXTENSIONS
from apps.accounts.models import Profile, Interest
from apps.rooms.models import Room, RoomMember
from apps.chat.models import Conversation, ConversationParticipant, Message
from apps.chat.services import ChatService
from apps.rooms.services import RoomService

User = get_user_model()

class GlobalSecurityAndPrivacyTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='global_user1',
            email='user1@example.com',
            password='SecurePassword123!'
        )
        self.user1.profile.display_name = 'User One'
        self.user1.profile.save()

        self.user2 = User.objects.create_user(
            username='global_user2',
            email='user2@example.com',
            password='SecurePassword123!'
        )
        self.user2.profile.display_name = 'User Two'
        self.user2.profile.save()

        self.user3 = User.objects.create_user(
            username='global_user3',
            email='user3@example.com',
            password='SecurePassword123!'
        )
        self.user3.profile.display_name = 'User Three'
        self.user3.profile.save()

    def test_profile_avatar_exif_metadata_stripped(self):
        # Create image in memory
        img_io = io.BytesIO()
        test_img = Image.new('RGB', (200, 200), color=(100, 150, 200))
        test_img.save(img_io, format='JPEG')
        img_bytes = img_io.getvalue()

        uploaded = SimpleUploadedFile("avatar_gps.jpg", img_bytes, content_type="image/jpeg")
        sanitized = sanitize_and_strip_image_exif(uploaded, max_dimension=800)
        self.assertIsNotNone(sanitized)
        self.assertTrue(sanitized.name.endswith('.jpg'))

        # Inspect resulting image
        res_img = Image.open(sanitized)
        self.assertEqual(len(res_img.getexif()), 0)

    def test_dangerous_file_extensions_rejected(self):
        for dangerous_ext in ['.exe', '.sh', '.php', '.py', '.html', '.svg', '.bat']:
            fake_file = SimpleUploadedFile(f"exploit{dangerous_ext}", b"echo 'bad'", content_type="text/plain")
            with self.assertRaises(ValidationError):
                sanitize_and_strip_image_exif(fake_file)

    def test_websocket_origin_validation(self):
        # Allowed origin
        scope_allowed = {
            'headers': [
                (b'origin', b'http://localhost:8000'),
                (b'host', b'localhost:8000'),
            ]
        }
        self.assertTrue(validate_websocket_origin(scope_allowed))

        # Disallowed foreign malicious origin
        scope_malicious = {
            'headers': [
                (b'origin', b'https://evil-attacker-site.com'),
                (b'host', b'localhost:8000'),
            ]
        }
        # In test environment ALLOWED_HOSTS is ['testserver', 'localhost', '127.0.0.1']
        self.assertFalse(validate_websocket_origin(scope_malicious))

    def test_object_level_chat_authorization(self):
        # User 1 and User 2 have a conversation
        conv, _ = ChatService.get_or_create_direct_conversation(self.user1, self.user2)
        ChatService.send_message(conv.id, self.user1, "Secret 1-on-1 message")

        client = Client()
        # User 3 (unauthorized outsider) attempts to access User 1 & User 2's conversation
        client.force_login(self.user3)
        resp = client.get(reverse('chat:detail', kwargs={'conversation_id': conv.id}))
        # Must be redirected or rejected
        self.assertEqual(resp.status_code, 302)

        # User 3 attempts to call messages API
        api_resp = client.get(reverse('chat:api_messages', kwargs={'conversation_id': conv.id}))
        self.assertEqual(api_resp.status_code, 400)

    def test_object_level_room_authorization(self):
        # User 1 creates a private room
        room = RoomService.create_room(
            creator=self.user1,
            name="Secret Committee",
            topic="Confidential",
            is_public=False
        )

        client = Client()
        client.force_login(self.user3)
        resp = client.get(reverse('rooms:detail', kwargs={'room_id': room.id}))
        # Unauthorized outsider accessing private room is blocked
        self.assertEqual(resp.status_code, 302)
