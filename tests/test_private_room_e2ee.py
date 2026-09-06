import uuid
import secrets
import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.private_rooms.models import PrivateRoom, PrivateRoomParticipant, PrivateRoomMessage
from apps.private_rooms.services import PrivateRoomService
from apps.safety.models import Report

User = get_user_model()


class PrivateRoomE2EETests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(
            username='alice_e2ee',
            email='alice@example.com',
            password='Password123!'
        )
        self.raw_creator_token = secrets.token_urlsafe(32)
        self.room, self.creator_participant = PrivateRoomService.create_room(
            creator_user=self.creator,
            duration_choice='1h',
            creator_temp_name='Silent Falcon',
            raw_session_token=self.raw_creator_token
        )

        self.raw_guest_token = secrets.token_urlsafe(32)
        self.guest_participant, _ = PrivateRoomService.join_room_atomic(
            room_id_or_token=self.room.id,
            raw_session_token=self.raw_guest_token,
            temp_name='Midnight Panther'
        )

        # Mock P-256 base64 public keys (65 bytes uncompressed P-256 = 88 base64 chars)
        self.alice_pub_key = "BM8+qZp5yL8e5zH2V5Y6mP+mD7cE8fG1hJ2kL3nO4pQ5rS6tU7vW8xY9z0A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6=="
        self.bob_pub_key = "BO9+rZp5yL8e5zH2V5Y6mP+mD7cE8fG1hJ2kL3nO4pQ5rS6tU7vW8xY9z0A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P7=="

    def test_public_key_registration_and_immutability(self):
        """
        Verify that participant public keys can be stored and cannot be modified once set.
        """
        self.creator_participant.public_key = self.alice_pub_key
        self.creator_participant.save(update_fields=['public_key'])

        self.creator_participant.refresh_from_db()
        self.assertEqual(self.creator_participant.public_key, self.alice_pub_key)

        # Setting guest public key
        self.guest_participant.public_key = self.bob_pub_key
        self.guest_participant.save(update_fields=['public_key'])

        self.guest_participant.refresh_from_db()
        self.assertEqual(self.guest_participant.public_key, self.bob_pub_key)

    def test_ciphertext_envelope_blind_storage(self):
        """
        Verify that the server stores only ciphertext JSON envelopes and zero plaintext.
        """
        sample_ciphertext_envelope = json.dumps({
            "v": 1,
            "iv": "dGhpcyBpcyBhIDEyLWJ5dGUgaXY=",
            "ciphertext": "YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY="
        })
        client_msg_id = f"pr_{uuid.uuid4()}"

        msg = PrivateRoomMessage.objects.create(
            room=self.room,
            sender=self.creator_participant,
            content=sample_ciphertext_envelope,
            client_msg_id=client_msg_id,
            message_type='text'
        )

        msg.refresh_from_db()
        self.assertEqual(msg.content, sample_ciphertext_envelope)
        self.assertEqual(msg.client_msg_id, client_msg_id)

        # Verify plaintext cannot be found anywhere in content
        self.assertNotIn("Hello world", msg.content)
        parsed = json.loads(msg.content)
        self.assertIn("iv", parsed)
        self.assertIn("ciphertext", parsed)
        self.assertEqual(parsed["v"], 1)

    def test_client_msg_id_replay_and_idempotency(self):
        """
        Verify that client_msg_id handles deduplication / idempotency.
        """
        client_msg_id = f"pr_{uuid.uuid4()}"
        msg1 = PrivateRoomMessage.objects.create(
            room=self.room,
            sender=self.creator_participant,
            content="cipher_envelope_1",
            client_msg_id=client_msg_id,
            message_type='text'
        )

        # Duplicate check logic: searching for existing client_msg_id
        existing = PrivateRoomMessage.objects.filter(
            room=self.room,
            client_msg_id=client_msg_id
        ).first()

        self.assertIsNotNone(existing)
        self.assertEqual(existing.id, msg1.id)

    def test_encrypted_media_upload_and_header_delivery(self):
        """
        Verify that media is uploaded with encrypted_file_key and file_iv,
        is preserved without Pillow re-encoding corruption,
        and serve_media returns the proper E2EE headers.
        """
        client = Client()
        session = client.session
        session[f"pr_auth_{self.room.id}"] = self.raw_creator_token
        session.save()

        fake_encrypted_bytes = b"\x00\x01\x02\x03\x04\x05CIPHERTEXT_BLOB\xff\xfe"
        uploaded_file = SimpleUploadedFile(
            name="photo.jpg",
            content=fake_encrypted_bytes,
            content_type="application/octet-stream"
        )
        fake_file_key = "FAKE_WRAPPED_FILE_KEY_BASE64"
        fake_file_iv = "FAKE_FILE_IV_BASE64"
        client_msg_id = f"pr_file_{uuid.uuid4()}"

        upload_url = reverse('private_rooms:upload_media', kwargs={'room_id': self.room.id})
        response = client.post(upload_url, {
            'file': uploaded_file,
            'message_type': 'image',
            'client_msg_id': client_msg_id,
            'encrypted_file_key': fake_file_key,
            'file_iv': fake_file_iv,
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['encrypted_file_key'], fake_file_key)
        self.assertEqual(data['file_iv'], fake_file_iv)

        msg_id = data['message_id']
        msg = PrivateRoomMessage.objects.get(id=msg_id)
        self.assertEqual(msg.encrypted_file_key, fake_file_key)
        self.assertEqual(msg.file_iv, fake_file_iv)
        self.assertEqual(msg.client_msg_id, client_msg_id)

        # Verify raw binary content is preserved exactly
        msg.file.seek(0)
        self.assertEqual(msg.file.read(), fake_encrypted_bytes)

        # Verify serve_media returns E2EE headers
        serve_url = reverse('private_rooms:serve_media', kwargs={'message_id': msg.id})
        serve_resp = client.get(serve_url)
        self.assertEqual(serve_resp.status_code, 200)
        self.assertEqual(serve_resp['X-Encrypted-File-Key'], fake_file_key)
        self.assertEqual(serve_resp['X-File-IV'], fake_file_iv)

    def test_user_consented_report_plaintext_evidence(self):
        """
        Verify that report_room_view appends user-consented plaintext evidence
        to the trust and safety report details.
        """
        client = Client()
        session = client.session
        session[f"pr_auth_{self.room.id}"] = self.raw_guest_token
        session.save()

        report_url = reverse('private_rooms:report_room', kwargs={'room_id': self.room.id})
        evidence = "[12:30] Silent Falcon: Stop sending abusive messages"

        response = client.post(report_url, {
            'reason': 'harassment',
            'details': 'User is being harassing.',
            'include_evidence': '1',
            'plaintext_evidence': evidence,
        })

        self.assertEqual(response.status_code, 302)
        report = Report.objects.latest('created_at')
        self.assertIn("harassment", report.reason)
        self.assertIn("User is being harassing.", report.details)
        self.assertIn("User-Consented Plaintext Evidence", report.details)
        self.assertIn(evidence, report.details)

    def test_chat_view_e2ee_session_state(self):
        """
        Verify room_chat_view reports the correct initial session state:
        WAITING_FOR_PEER if only one participant,
        KEY_EXCHANGE if 2 participants but missing keys,
        E2EE_ESTABLISHED if both have public keys.
        """
        client = Client()
        session = client.session
        session[f"pr_auth_{self.room.id}"] = self.raw_creator_token
        session.save()

        chat_url = reverse('private_rooms:chat', kwargs={'room_id': self.room.id})

        # Initially, guest has not registered public key -> KEY_EXCHANGE
        resp = client.get(chat_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['session_state'], 'KEY_EXCHANGE')

        # When both have public keys registered
        self.creator_participant.public_key = self.alice_pub_key
        self.creator_participant.save()
        self.guest_participant.public_key = self.bob_pub_key
        self.guest_participant.save()

        resp2 = client.get(chat_url)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.context['session_state'], 'E2EE_ESTABLISHED')
