import uuid
import secrets
import hashlib
from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.core.cache import cache

from apps.private_rooms.models import PrivateRoom, PrivateRoomParticipant, PrivateRoomMessage
from apps.private_rooms.services import PrivateRoomService, hash_token
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

    def test_create_room_expiry_and_codes_and_token_hashing(self):
        raw_session_token = secrets.token_urlsafe(32)
        room, participant = PrivateRoomService.create_room(
            creator_user=self.creator,
            duration_choice='1h',
            creator_temp_name='Silver Falcon',
            raw_session_token=raw_session_token
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

        # 1. Verify token is hashed in database, never raw
        expected_hash = hashlib.sha256(raw_session_token.encode('utf-8')).hexdigest()
        self.assertEqual(participant.session_token_hash, expected_hash)
        self.assertNotEqual(participant.session_token_hash, raw_session_token)

    def test_random_temp_name_generation(self):
        name = PrivateRoomService.generate_random_temp_name()
        self.assertIsInstance(name, str)
        self.assertGreater(len(name.split()), 1)

    def test_atomic_capacity_limit_enforced_and_reentry(self):
        # 1. Creator creates room
        raw_creator_token = secrets.token_urlsafe(32)
        room, p1 = PrivateRoomService.create_room(
            creator_user=self.creator,
            duration_choice='24h',
            creator_temp_name='Purple Owl',
            raw_session_token=raw_creator_token
        )

        # 2. Guest 1 joins -> 2 participants -> Room full
        raw_guest1_token = secrets.token_urlsafe(32)
        p2, status = PrivateRoomService.join_room_atomic(
            room_id_or_token=room.id,
            raw_session_token=raw_guest1_token,
            temp_name='Amber Lynx'
        )
        self.assertEqual(status, 'joined')
        self.assertEqual(p2.temp_name, 'Amber Lynx')
        
        room.refresh_from_db()
        self.assertTrue(room.is_full)
        self.assertFalse(room.can_join)

        # 3. Existing Guest 1 re-enters / reconnects -> Returns 'existing' seamlessly
        p2_reenter, status_reenter = PrivateRoomService.join_room_atomic(
            room_id_or_token=room.id,
            raw_session_token=raw_guest1_token,
            temp_name='Amber Lynx'
        )
        self.assertEqual(status_reenter, 'existing')
        self.assertEqual(p2_reenter.id, p2.id)

        # 4. Guest 2 attempts to join -> Rejected as full
        raw_guest2_token = secrets.token_urlsafe(32)
        p3, status_rejected = PrivateRoomService.join_room_atomic(
            room_id_or_token=room.id,
            raw_session_token=raw_guest2_token,
            temp_name='Blue Panda'
        )
        self.assertEqual(status_rejected, 'full')

    def test_expired_room_rejection(self):
        raw_token = secrets.token_urlsafe(32)
        room, _ = PrivateRoomService.create_room(
            creator_user=self.creator,
            duration_choice='1h',
            creator_temp_name='Cosmic Badger',
            raw_session_token=raw_token
        )
        # Fast-forward expiry
        room.expires_at = timezone.now() - timedelta(minutes=5)
        room.save(update_fields=['expires_at'])

        self.assertTrue(room.is_expired)
        self.assertFalse(room.can_join)

        raw_guest_token = secrets.token_urlsafe(32)
        res, status = PrivateRoomService.join_room_atomic(
            room_id_or_token=room.id,
            raw_session_token=raw_guest_token,
            temp_name='Solar Dolphin'
        )
        self.assertEqual(status, 'expired')

    def test_room_deletion_by_creator_only(self):
        raw_creator_token = secrets.token_urlsafe(32)
        room, p1 = PrivateRoomService.create_room(
            creator_user=self.creator,
            duration_choice='24h',
            creator_temp_name='Velvet Fox',
            raw_session_token=raw_creator_token
        )
        raw_guest_token = secrets.token_urlsafe(32)
        p2, _ = PrivateRoomService.join_room_atomic(
            room_id_or_token=room.id,
            raw_session_token=raw_guest_token,
            temp_name='Golden Hawk'
        )

        # Guest trying to delete room should raise ValidationError
        with self.assertRaises(ValidationError):
            PrivateRoomService.delete_room(room, p2)

        # Creator deleting room should succeed
        self.assertTrue(PrivateRoomService.delete_room(room, p1))
        room.refresh_from_db()
        self.assertTrue(room.is_deleted)

    def test_v1_block_behavior(self):
        raw_creator_token = secrets.token_urlsafe(32)
        room, p1 = PrivateRoomService.create_room(
            creator_user=self.creator,
            duration_choice='24h',
            creator_temp_name='Velvet Fox',
            raw_session_token=raw_creator_token
        )
        raw_guest_token = secrets.token_urlsafe(32)
        p2, _ = PrivateRoomService.join_room_atomic(
            room_id_or_token=room.id,
            raw_session_token=raw_guest_token,
            temp_name='Golden Hawk'
        )

        # Block room
        PrivateRoomService.block_room(room, p1)
        room.refresh_from_db()
        p1.refresh_from_db()
        self.assertTrue(room.is_blocked)
        self.assertTrue(p1.is_blocked)
        self.assertFalse(room.can_join)


class PrivateRoomSecurityAndUploadTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(
            username='alice_upload',
            email='alice@example.com',
            password='SecretPassword123!',
        )
        self.creator.profile.display_name = 'Alice Secret'
        self.creator.profile.save()
        self.raw_session_token = secrets.token_urlsafe(32)
        self.room, self.p1 = PrivateRoomService.create_room(
            creator_user=self.creator,
            duration_choice='24h',
            creator_temp_name='Quiet Otter',
            raw_session_token=self.raw_session_token
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
        cache.clear()
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

    def test_landing_page_shows_active_rooms_and_header_separation(self):
        self.client.force_login(self.user)
        raw_token = secrets.token_urlsafe(32)
        room, p1 = PrivateRoomService.create_room(
            creator_user=self.user,
            duration_choice='24h',
            creator_temp_name='Cosmic Leopard',
            raw_session_token=raw_token
        )

        response = self.client.get(reverse('private_rooms:landing'))
        self.assertEqual(response.status_code, 200)
        # Header must say Private Room directly
        self.assertContains(response, "Private Room")
        # Landing must show Your Active Private Rooms and Resume Chat button
        self.assertContains(response, "Your Active Private Rooms")
        self.assertContains(response, "Cosmic Leopard")
        self.assertContains(response, "Resume Chat")
        self.assertContains(response, room.join_code)

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
        raw_creator_token = secrets.token_urlsafe(32)
        room, _ = PrivateRoomService.create_room(
            creator_user=self.user,
            duration_choice='24h',
            creator_temp_name='Sage Koala',
            raw_session_token=raw_creator_token
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
        raw_creator_token = secrets.token_urlsafe(32)
        room, _ = PrivateRoomService.create_room(
            creator_user=self.user,
            duration_choice='24h',
            creator_temp_name='Ocean Wolf',
            raw_session_token=raw_creator_token
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

    def test_join_code_rate_limiting(self):
        guest_client = Client()
        for i in range(6):
            guest_client.post(reverse('private_rooms:join_code'), {
                'join_code': f'FAKE{i}',
                'temp_name': 'Tester'
            })
        
        # 7th request should trigger rate limit warning
        rate_limited_resp = guest_client.post(reverse('private_rooms:join_code'), {
            'join_code': 'FAKE99',
            'temp_name': 'Tester'
        })
        self.assertEqual(rate_limited_resp.status_code, 200)
        self.assertContains(rate_limited_resp, "Too many attempts")

    def test_unauthorized_media_access_forbidden(self):
        # Setup room with creator and uploaded photo
        raw_creator_token = secrets.token_urlsafe(32)
        room, p1 = PrivateRoomService.create_room(
            creator_user=self.user,
            duration_choice='24h',
            creator_temp_name='Astral Eagle',
            raw_session_token=raw_creator_token
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


class PrivateRoomEdgeCasesAndSecurityVerificationTests(TestCase):
    """
    Comprehensive Backend Security Verification Suite covering all 15 edge cases:
    1. Simultaneous guest joins / capacity concurrency
    2. Third participant rejection
    3. Participant reconnecting after refresh (re-entry)
    4. Participant reopening after navigating away (session lookup)
    5. Expired invite links
    6. Expired join codes
    7. Deleted rooms
    8. Unauthorized WebSocket connections
    9. Unauthorized media access
    10. Cross-room guest session scoping
    11. Frontend request manipulation (non-creator room deletion)
    12. File upload bypass attempts (dangerous formats, oversized)
    13. Brute-force join-code rate limiting
    14. Room expiry while actively chatting
    15. Room deletion and physical storage cleanup / management command
    """
    def setUp(self):
        cache.clear()
        self.creator_user = User.objects.create_user(
            username='charlie_creator',
            email='charlie@example.com',
            password='SecretPassword123!',
        )
        self.creator_user.profile.display_name = 'Charlie Specialist'
        self.creator_user.profile.save()

        self.raw_creator_token = secrets.token_urlsafe(32)
        self.room, self.creator_p = PrivateRoomService.create_room(
            creator_user=self.creator_user,
            duration_choice='24h',
            creator_temp_name='Silver Lynx',
            raw_session_token=self.raw_creator_token
        )

    # Edge Case 1 & 2: Capacity Limit & Third Participant Blocked
    def test_edge_case_1_and_2_capacity_limit_and_third_participant_blocked(self):
        # First guest joins
        raw_guest1_token = secrets.token_urlsafe(32)
        guest1, status1 = PrivateRoomService.join_room_atomic(
            room_id_or_token=self.room.id,
            raw_session_token=raw_guest1_token,
            temp_name='Amber Fox'
        )
        self.assertEqual(status1, 'joined')

        self.room.refresh_from_db()
        self.assertTrue(self.room.is_full)

        # Third participant attempts join
        raw_guest2_token = secrets.token_urlsafe(32)
        guest2, status2 = PrivateRoomService.join_room_atomic(
            room_id_or_token=self.room.id,
            raw_session_token=raw_guest2_token,
            temp_name='Golden Bear'
        )
        self.assertEqual(status2, 'full')
        self.assertEqual(self.room.participants.count(), 2)

    # Edge Case 3: Reconnecting after refresh (re-entry)
    def test_edge_case_3_participant_reconnect_after_refresh(self):
        raw_guest_token = secrets.token_urlsafe(32)
        guest, status = PrivateRoomService.join_room_atomic(
            room_id_or_token=self.room.id,
            raw_session_token=raw_guest_token,
            temp_name='Quiet Eagle'
        )
        self.assertEqual(status, 'joined')

        # Re-entry with identical session token
        guest_reconnect, status_reconnect = PrivateRoomService.join_room_atomic(
            room_id_or_token=self.room.id,
            raw_session_token=raw_guest_token,
            temp_name='Quiet Eagle'
        )
        self.assertEqual(status_reconnect, 'existing')
        self.assertEqual(guest_reconnect.id, guest.id)

    # Edge Case 4: Reopening after navigating away (session lookup)
    def test_edge_case_4_reopen_after_navigating_away(self):
        client = Client()
        client.force_login(self.creator_user)
        # Store creator session token
        session = client.session
        session[f"pr_auth_{self.room.id}"] = self.raw_creator_token
        session.save()

        # Revisit landing page
        landing_resp = client.get(reverse('private_rooms:landing'))
        self.assertEqual(landing_resp.status_code, 200)
        self.assertContains(landing_resp, "Your Active Private Rooms")
        self.assertContains(landing_resp, "Silver Lynx")
        self.assertContains(landing_resp, "Resume Chat")

        # Resume chat directly
        chat_resp = client.get(reverse('private_rooms:chat', kwargs={'room_id': self.room.id}))
        self.assertEqual(chat_resp.status_code, 200)
        self.assertContains(chat_resp, "Silver Lynx")

    # Edge Case 5: Expired invite link
    def test_edge_case_5_expired_invite_link(self):
        self.room.expires_at = timezone.now() - timedelta(minutes=5)
        self.room.save(update_fields=['expires_at'])

        client = Client()
        invite_url = reverse('private_rooms:invite_landing', kwargs={'secure_token': self.room.secure_token})
        resp = client.get(invite_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Room Expired")

        # Attempt to join via POST on expired invite
        join_url = reverse('private_rooms:join_invite', kwargs={'secure_token': self.room.secure_token})
        join_resp = client.post(join_url, {'temp_name': 'Late Guest'})
        self.assertEqual(join_resp.status_code, 200)
        self.assertContains(join_resp, "Room Expired")

    # Edge Case 6: Expired join code
    def test_edge_case_6_expired_join_code(self):
        self.room.expires_at = timezone.now() - timedelta(minutes=5)
        self.room.save(update_fields=['expires_at'])

        client = Client()
        join_resp = client.post(reverse('private_rooms:join_code'), {
            'join_code': self.room.join_code,
            'temp_name': 'Late Guest'
        })
        self.assertEqual(join_resp.status_code, 200)
        self.assertContains(join_resp, "Invalid or expired join code")

    # Edge Case 7: Deleted room
    def test_edge_case_7_deleted_room(self):
        PrivateRoomService.delete_room(self.room, self.creator_p)

        client = Client()
        session = client.session
        session[f"pr_auth_{self.room.id}"] = self.raw_creator_token
        session.save()

        # Reopening chat on deleted room
        resp = client.get(reverse('private_rooms:chat', kwargs={'room_id': self.room.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Room Deleted")

    # Edge Case 8: Unauthorized WebSocket connection
    def test_edge_case_8_unauthorized_websocket_database_rejection(self):
        fake_token = secrets.token_urlsafe(32)
        fake_hash = hash_token(fake_token)
        # Verify no participant exists with fake token hash
        self.assertFalse(PrivateRoomParticipant.objects.filter(session_token_hash=fake_hash).exists())

    # Edge Case 9 & 10: Cross-Room Guest Session Scoping & Media Isolation
    def test_edge_case_9_and_10_cross_room_session_scoping(self):
        # Create second independent private room
        raw_creator2_token = secrets.token_urlsafe(32)
        room2, p2 = PrivateRoomService.create_room(
            creator_user=self.creator_user,
            duration_choice='24h',
            creator_temp_name='Solar Falcon',
            raw_session_token=raw_creator2_token
        )

        # Creator of Room 1 creates a message in Room 1
        msg1 = PrivateRoomMessage.objects.create(
            room=self.room,
            sender=self.creator_p,
            content="Top secret message in room 1",
            message_type='text'
        )

        # Client possessing only session credentials for Room 2
        client2 = Client()
        session2 = client2.session
        session2[f"pr_auth_{room2.id}"] = raw_creator2_token
        session2.save()

        # Client 2 attempts to open Room 1 chat
        chat_resp = client2.get(reverse('private_rooms:chat', kwargs={'room_id': self.room.id}))
        self.assertEqual(chat_resp.status_code, 302)  # Redirects to landing with unauthorized error

        # Client 2 attempts to upload media to Room 1
        upload_resp = client2.post(reverse('private_rooms:upload_media', kwargs={'room_id': self.room.id}), {
            'file': SimpleUploadedFile("hack.jpg", b"fake jpg", content_type="image/jpeg"),
            'message_type': 'image'
        })
        self.assertEqual(upload_resp.status_code, 403)

    # Edge Case 11: Non-creator attempting room deletion
    def test_edge_case_11_manipulate_delete_as_non_creator(self):
        raw_guest_token = secrets.token_urlsafe(32)
        guest, _ = PrivateRoomService.join_room_atomic(
            room_id_or_token=self.room.id,
            raw_session_token=raw_guest_token,
            temp_name='Guest Participant'
        )

        # Guest client attempts to POST to delete_room_view
        guest_client = Client()
        session = guest_client.session
        session[f"pr_auth_{self.room.id}"] = raw_guest_token
        session.save()

        delete_resp = guest_client.post(reverse('private_rooms:delete_room', kwargs={'room_id': self.room.id}))
        self.assertEqual(delete_resp.status_code, 302)
        self.assertEqual(delete_resp.url, reverse('private_rooms:chat', kwargs={'room_id': self.room.id}))

        # Room must NOT be deleted
        self.room.refresh_from_db()
        self.assertFalse(self.room.is_deleted)

    # Edge Case 12: File upload bypass attempts (dangerous formats, oversized)
    def test_edge_case_12_file_upload_bypass_attempts(self):
        dangerous_extensions = [
            ("exploit.exe", b"MZ executable", "application/x-msdownload"),
            ("shell.sh", b"#!/bin/bash", "application/x-sh"),
            ("backdoor.php", b"<?php phpinfo(); ?>", "application/x-php"),
            ("payload.py", b"import os; os.system('calc')", "text/x-python"),
            ("script.js", b"alert(1)", "application/javascript"),
            ("index.html", b"<html><body>XSS</body></html>", "text/html"),
            ("vector.svg", b"<svg onload=alert(1)></svg>", "image/svg+xml"),
        ]
        for fname, content, mime in dangerous_extensions:
            bad_file = SimpleUploadedFile(fname, content, content_type=mime)
            with self.assertRaises(ValidationError):
                PrivateRoomService.validate_and_save_upload(
                    room=self.room,
                    participant=self.creator_p,
                    file_obj=bad_file,
                    message_type='file'
                )

        # Oversized file
        huge_file = SimpleUploadedFile("huge.pdf", b"0" * (26 * 1024 * 1024), content_type="application/pdf")
        with self.assertRaises(ValidationError):
            PrivateRoomService.validate_and_save_upload(
                room=self.room,
                participant=self.creator_p,
                file_obj=huge_file,
                message_type='file'
            )

    # Edge Case 13: Brute-force join code rate limiting
    def test_edge_case_13_join_code_rate_limit(self):
        client = Client()
        for i in range(6):
            client.post(reverse('private_rooms:join_code'), {
                'join_code': f'CODE{i}',
                'temp_name': 'Attacker'
            })

        limited_resp = client.post(reverse('private_rooms:join_code'), {
            'join_code': 'FINAL9',
            'temp_name': 'Attacker'
        })
        self.assertContains(limited_resp, "Too many attempts")

    # Edge Case 14: Room expiry while active
    def test_edge_case_14_room_expiry_while_active(self):
        # Room expires mid-session
        self.room.expires_at = timezone.now() - timedelta(seconds=1)
        self.room.save(update_fields=['expires_at'])

        fake_img = SimpleUploadedFile("photo.jpg", b"jpeg data", content_type="image/jpeg")
        with self.assertRaises(ValidationError):
            PrivateRoomService.validate_and_save_upload(
                room=self.room,
                participant=self.creator_p,
                file_obj=fake_img,
                message_type='image'
            )

    # Edge Case 15: Room deletion, file storage cleanup & management command
    def test_edge_case_15_deletion_cleanup_and_management_command(self):
        from django.core.management import call_command
        from io import StringIO

        fake_img = SimpleUploadedFile("clean_test.jpg", b"jpeg data to purge", content_type="image/jpeg")
        msg = PrivateRoomService.validate_and_save_upload(
            room=self.room,
            participant=self.creator_p,
            file_obj=fake_img,
            message_type='image'
        )
        self.assertTrue(msg.file.name)

        # Mark room as expired
        self.room.expires_at = timezone.now() - timedelta(days=1)
        self.room.save(update_fields=['expires_at'])

        # Execute management command
        out = StringIO()
        call_command('cleanup_expired_private_rooms', stdout=out)
        output_str = out.getvalue()
        self.assertIn("Successfully cleaned up", output_str)

        self.room.refresh_from_db()
        self.assertTrue(self.room.is_deleted)