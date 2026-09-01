import uuid
import secrets
from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError

from apps.private_rooms.models import PrivateRoom, PrivateRoomParticipant, PrivateRoomMessage
from apps.private_rooms.services import PrivateRoomService
from apps.safety.models import Report

User = get_user_model()


class PrivateRoomModelAndServiceTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(
            username='alice_creator',
            email='creator@example.com',
            password='SecretPassword123!',
        )
        self.creator.profile.display_name = 'Alice Wonderland'
        self.creator.profile.save()

    def test_create_room_expiry_and_codes(self):
        session_key = secrets.token_urlsafe(32)
        room, participant = PrivateRoomService.create_room(
            creator_user=self.creator,
            duration_choice='1h',
            creator_temp_name='Silver Falcon',
            session_key=session_key
        )
        self.assertIsNotNone(room.id)
        self.assertEqual(len(room.join_code), 6)
        self.assertTrue(room.join_code.isupper())
        self.assertTrue(len(room.secure_token) >= 32)
        self.assertFalse(room.is_expired)
        self.assertTrue(room.can_join)
        self.assertEqual(room.creator, self.creator)
        self.assertEqual(participant.temp_name, 'Silver Falcon')
        self.assertTrue(participant.is_creator)

    def test_random_temp_name_generation(self):
        name = PrivateRoomService.generate_random_temp_name()
        self.assertIsInstance(name, str)
        self.assertGreater(len(name.split()), 1)

    def test_atomic_capacity_limit_enforced(self):
        # 1. Creator creates room
        session_creator = secrets.token_urlsafe(32)
        room, p1 = PrivateRoomService.create_room(
            creator_user=self.creator,
            duration_choice='24h',
            creator_temp_name='Purple Owl',
            session_key=session_creator
        )

        # 2. Guest 1 joins -> 2 participants -> Room full
        session_guest1 = secrets.token_urlsafe(32)
        p2, status = PrivateRoomService.join_room_atomic(
            room_id_or_token=room.id,
            session_key=session_guest1,
            temp_name='Amber Lynx'
        )
        self.assertEqual(status, 'joined')
        self.assertEqual(p2.temp_name, 'Amber Lynx')
        
        room.refresh_from_db()
        self.assertTrue(room.is_full)
        self.assertFalse(room.can_join)

        # 3. Guest 2 attempts to join -> Rejected as full
        session_guest2 = secrets.token_urlsafe(32)
        p3, status_rejected = PrivateRoomService.join_room_atomic(
            room_id_or_token=room.id,
            session_key=session_guest2,
            temp_name='Blue Panda'
        )
        self.assertEqual(status_rejected, 'full')

    def test_expired_room_rejection(self):
        session_key = secrets.token_urlsafe(32)
        room, _ = PrivateRoomService.create_room(
            creator_user=self.creator,
            duration_choice='1h',
            creator_temp_name='Cosmic Badger',
            session_key=session_key
        )
        # Fast-forward expiry
        room.expires_at = timezone.now() - timedelta(minutes=5)
        room.save(update_fields=['expires_at'])

        self.assertTrue(room.is_expired)
        self.assertFalse(room.can_join)

        session_guest = secrets.token_urlsafe(32)
        res, status = PrivateRoomService.join_room_atomic(
            room_id_or_token=room.id,
            session_key=session_guest,
            temp_name='Solar Dolphin'
        )
        self.assertEqual(status, 'expired')

    def test_room_deletion_by_creator_only(self):
        session_creator = secrets.token_urlsafe(32)
        room, p1 = PrivateRoomService.create_room(
            creator_user=self.creator,
            duration_choice='24h',
            creator_temp_name='Velvet Fox',
            session_key=session_creator
        )
        session_guest = secrets.token_urlsafe(32)
        p2, _ = PrivateRoomService.join_room_atomic(
            room_id_or_token=room.id,
            session_key=session_guest,
            temp_name='Golden Hawk'
        )

        # Guest trying to delete room should raise ValidationError
        with self.assertRaises(ValidationError):
            PrivateRoomService.delete_room(room, p2)

        # Creator deleting room should succeed
        self.assertTrue(PrivateRoomService.delete_room(room, p1))
        room.refresh_from_db()
        self.assertTrue(room.is_deleted)


class PrivateRoomSecurityAndUploadTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(
            username='alice_upload',
            email='alice@example.com',
            password='SecretPassword123!',
        )
        self.creator.profile.display_name = 'Alice Secret'
        self.creator.profile.save()
        self.session_key = secrets.token_urlsafe(32)
        self.room, self.p1 = PrivateRoomService.create_room(
            creator_user=self.creator,
            duration_choice='24h',
            creator_temp_name='Quiet Otter',
            session_key=self.session_key
        )

    def test_valid_image_upload(self):
        fake_img = SimpleUploadedFile("test_photo.jpg", b"fake jpeg image data", content_type="image/jpeg")
        msg = PrivateRoomService.validate_and_save_upload(
            room=self.room,
            participant=self.p1,
            file_obj=fake_img,
            message_type='image'
        )
        self.assertEqual(msg.message_type, 'image')
        self.assertEqual(msg.sender, self.p1)
        self.assertTrue(msg.file.name.endswith('.jpg'))

    def test_valid_voice_upload(self):
        fake_audio = SimpleUploadedFile("voice.webm", b"fake webm audio chunk", content_type="audio/webm")
        msg = PrivateRoomService.validate_and_save_upload(
            room=self.room,
            participant=self.p1,
            file_obj=fake_audio,
            message_type='audio'
        )
        self.assertEqual(msg.message_type, 'audio')
        self.assertEqual(msg.sender, self.p1)

    def test_disallowed_executable_upload_blocked(self):
        dangerous_files = [
            ("virus.exe", b"dangerous exe binary", "application/x-msdownload"),
            ("script.sh", b"#!/bin/bash echo hacked", "application/x-sh"),
            ("payload.php", b"<?php phpinfo(); ?>", "application/x-php"),
            ("malicious.js", b"alert(1)", "application/javascript"),
        ]
        for fname, data, ctype in dangerous_files:
            bad_file = SimpleUploadedFile(fname, data, content_type=ctype)
            with self.assertRaises(ValidationError):
                PrivateRoomService.validate_and_save_upload(
                    room=self.room,
                    participant=self.p1,
                    file_obj=bad_file,
                    message_type='file'
                )


class PrivateRoomViewsHTTPTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='bob_view',
            email='bob@example.com',
            password='SecretPassword123!',
        )
        self.user.profile.display_name = 'Bob Developer'
        self.user.profile.save()

    def test_landing_page(self):
        response = self.client.get(reverse('private_rooms:landing'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Private Room")
        self.assertContains(response, "Join with Code")

    def test_create_private_room_flow(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('private_rooms:create'), {
            'duration': '24h',
            'temp_name': 'Emerald Jaguar'
        })
        self.assertEqual(response.status_code, 302)
        
        room = PrivateRoom.objects.first()
        self.assertIsNotNone(room)
        self.assertEqual(room.creator_temp_name, 'Emerald Jaguar')

        # Follow redirect to created share page
        share_response = self.client.get(response.url)
        self.assertEqual(share_response.status_code, 200)
        self.assertContains(share_response, room.join_code)
        self.assertContains(share_response, room.secure_token)

    def test_guest_join_by_invite_url(self):
        # Creator creates room
        session_creator = secrets.token_urlsafe(32)
        room, _ = PrivateRoomService.create_room(
            creator_user=self.user,
            duration_choice='24h',
            creator_temp_name='Sage Koala',
            session_key=session_creator
        )

        # Unauthenticated guest opens invite page
        guest_client = Client()
        invite_url = reverse('private_rooms:invite_landing', kwargs={'secure_token': room.secure_token})
        resp = guest_client.get(invite_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "You've Been Invited")

        # Guest submits join form
        join_url = reverse('private_rooms:join_invite', kwargs={'secure_token': room.secure_token})
        post_resp = guest_client.post(join_url, {'temp_name': 'Mystic Tiger'})
        self.assertEqual(post_resp.status_code, 302)
        
        # Follow to chat room
        chat_resp = guest_client.get(post_resp.url)
        self.assertEqual(chat_resp.status_code, 200)
        self.assertContains(chat_resp, 'Mystic Tiger')
        self.assertNotContains(chat_resp, self.user.email)
        self.assertNotContains(chat_resp, self.user.profile.get_display_name())

    def test_guest_join_by_join_code(self):
        session_creator = secrets.token_urlsafe(32)
        room, _ = PrivateRoomService.create_room(
            creator_user=self.user,
            duration_choice='24h',
            creator_temp_name='Ocean Wolf',
            session_key=session_creator
        )

        guest_client = Client()
        join_resp = guest_client.post(reverse('private_rooms:join_code'), {
            'join_code': room.join_code,
            'temp_name': 'Frost Bear'
        })
        self.assertEqual(join_resp.status_code, 302)
        
        chat_resp = guest_client.get(join_resp.url)
        self.assertEqual(chat_resp.status_code, 200)
        self.assertContains(chat_resp, 'Frost Bear')

    def test_unauthorized_media_access_forbidden(self):
        # Setup room with creator and uploaded photo
        session_creator = secrets.token_urlsafe(32)
        room, p1 = PrivateRoomService.create_room(
            creator_user=self.user,
            duration_choice='24h',
            creator_temp_name='Astral Eagle',
            session_key=session_creator
        )
        fake_img = SimpleUploadedFile("secret_photo.png", b"secret png binary", content_type="image/png")
        msg = PrivateRoomService.validate_and_save_upload(
            room=room,
            participant=p1,
            file_obj=fake_img,
            message_type='image'
        )

        media_url = reverse('private_rooms:serve_media', kwargs={'message_id': msg.id})

        # Random unauthorized client attempting to access media
        unauthorized_client = Client()
        resp = unauthorized_client.get(media_url)
        self.assertEqual(resp.status_code, 403)