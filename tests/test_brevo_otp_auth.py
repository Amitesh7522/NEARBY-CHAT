"""
Automated unit & integration tests for Real Brevo Email OTP Authentication System.
Covers: Valid OTP, Invalid OTP, Expired OTP, Reused OTP, Resend Cooldown,
Rate Limiting, Max Attempts, Duplicate Email, Brevo API Error Handling, and Case-Insensitive Normalization.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
import json
from unittest.mock import patch, MagicMock
import urllib.error

from apps.accounts.models import OTPVerification, Profile
from apps.accounts.services import (
    VerificationService, BrevoEmailProvider, hash_otp, generate_secure_otp
)

User = get_user_model()

class BrevoEmailOTPAuthTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.test_email = "alex.dev@nearbychat.in"
        self.test_password = "SecurePassword123!"

    @patch('apps.accounts.services.BrevoEmailProvider.send_otp')
    def test_send_otp_success_and_hashed_storage(self, mock_send_otp):
        """Dispatches OTP via Brevo and ensures plaintext OTP is NEVER stored in database."""
        mock_send_otp.return_value = (True, "Verification code sent to your email.")

        success, msg, cooldown = VerificationService.send_otp_challenge(self.test_email, purpose='signup')
        self.assertTrue(success)
        self.assertEqual(cooldown, 60)

        # Check DB record
        record = OTPVerification.objects.filter(identifier=self.test_email, is_used=False).first()
        self.assertIsNotNone(record)
        self.assertFalse(record.is_used)
        self.assertEqual(record.attempts, 0)
        # Ensure plaintext OTP is NOT in database (only 64-char sha256 hash)
        self.assertEqual(len(record.otp_hash), 64)

    @patch('apps.accounts.services.BrevoEmailProvider.send_otp')
    def test_valid_otp_and_registration_flow(self, mock_send_otp):
        """User registers with valid Email OTP and is redirected to onboarding."""
        mock_send_otp.return_value = (True, "Verification code sent to your email.")

        # Simulate user requesting OTP
        raw_otp = "481920"
        expires_at = timezone.now() + timedelta(minutes=10)
        OTPVerification.objects.create(
            identifier=self.test_email,
            otp_hash=hash_otp(raw_otp),
            purpose='signup',
            expires_at=expires_at,
        )

        # Submit Step 1 registration form
        form_data = {
            'auth_type': 'email',
            'identifier': self.test_email,
            'otp': raw_otp,
            'password': self.test_password,
            'confirm_password': self.test_password,
        }
        response = self.client.post(reverse('accounts:register'), data=form_data)
        self.assertRedirects(response, reverse('accounts:onboarding'))

        # Check user created
        user = User.objects.filter(email=self.test_email).first()
        self.assertIsNotNone(user)
        self.assertTrue(user.is_verified)
        self.assertTrue(user.username.startswith('user_'))
        self.assertTrue(user.profile.is_temporary_name)

    def test_invalid_otp_verification(self):
        """Verifying with an incorrect OTP decrements remaining attempts."""
        raw_otp = "654321"
        OTPVerification.objects.create(
            identifier=self.test_email,
            otp_hash=hash_otp(raw_otp),
            purpose='signup',
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        is_valid, msg = VerificationService.verify_otp_challenge(self.test_email, "000000", purpose='signup')
        self.assertFalse(is_valid)
        self.assertIn("Incorrect verification code", msg)

        # Check attempts count in DB
        record = OTPVerification.objects.get(identifier=self.test_email)
        self.assertEqual(record.attempts, 1)

    def test_expired_otp_rejected(self):
        """Expired OTP is rejected and automatically marked as used."""
        raw_otp = "777888"
        expired_time = timezone.now() - timedelta(minutes=1)
        OTPVerification.objects.create(
            identifier=self.test_email,
            otp_hash=hash_otp(raw_otp),
            purpose='signup',
            expires_at=expired_time,
        )

        is_valid, msg = VerificationService.verify_otp_challenge(self.test_email, raw_otp, purpose='signup')
        self.assertFalse(is_valid)
        self.assertIn("expired", msg.lower())

    def test_reused_otp_rejected(self):
        """Once verified, an OTP cannot be reused."""
        raw_otp = "112233"
        OTPVerification.objects.create(
            identifier=self.test_email,
            otp_hash=hash_otp(raw_otp),
            purpose='signup',
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        # 1st verification: Success
        is_valid1, _ = VerificationService.verify_otp_challenge(self.test_email, raw_otp, purpose='signup')
        self.assertTrue(is_valid1)

        # 2nd verification: Rejected
        is_valid2, msg2 = VerificationService.verify_otp_challenge(self.test_email, raw_otp, purpose='signup')
        self.assertFalse(is_valid2)

    @patch('apps.accounts.services.BrevoEmailProvider.send_otp')
    def test_resend_cooldown_enforcement(self, mock_send_otp):
        """Requesting another OTP within 60 seconds triggers a cooldown restriction."""
        mock_send_otp.return_value = (True, "Sent")

        # 1st request: Success
        success1, _, cooldown1 = VerificationService.send_otp_challenge(self.test_email, purpose='signup')
        self.assertTrue(success1)
        self.assertEqual(cooldown1, 60)

        # 2nd immediate request (< 60s): Rejection with cooldown
        success2, msg2, cooldown2 = VerificationService.send_otp_challenge(self.test_email, purpose='signup')
        self.assertFalse(success2)
        self.assertIn("wait", msg2.lower())
        self.assertGreater(cooldown2, 0)
        self.assertLessEqual(cooldown2, 60)

    @patch('apps.accounts.services.BrevoEmailProvider.send_otp')
    def test_hourly_rate_limiting(self, mock_send_otp):
        """Requesting more than 5 OTPs within 1 hour triggers rate limit protection."""
        mock_send_otp.return_value = (True, "Sent")
        now = timezone.now()

        # Seed 5 requests in the past hour
        for i in range(5):
            OTPVerification.objects.create(
                identifier=self.test_email,
                otp_hash=hash_otp(f"10000{i}"),
                purpose='signup',
                expires_at=now + timedelta(minutes=10),
                is_used=True,
                created_at=now - timedelta(minutes=30 - i),
            )

        # 6th request: Rate limited
        success, msg, cooldown = VerificationService.send_otp_challenge(self.test_email, purpose='signup')
        self.assertFalse(success)
        self.assertIn("too many", msg.lower())

    def test_maximum_failed_attempts_invalidation(self):
        """5 failed OTP attempts invalidates the record completely."""
        raw_otp = "998877"
        record = OTPVerification.objects.create(
            identifier=self.test_email,
            otp_hash=hash_otp(raw_otp),
            purpose='signup',
            expires_at=timezone.now() + timedelta(minutes=10),
            attempts=4
        )

        # 5th failed attempt
        is_valid, msg = VerificationService.verify_otp_challenge(self.test_email, "000000", purpose='signup')
        self.assertFalse(is_valid)
        self.assertIn("too many failed attempts", msg.lower())

        record.refresh_from_db()
        self.assertTrue(record.is_used)

        # Subsequent attempt with the CORRECT otp is now rejected because it was invalidated
        is_valid_after, _ = VerificationService.verify_otp_challenge(self.test_email, raw_otp, purpose='signup')
        self.assertFalse(is_valid_after)

    def test_duplicate_email_rejection_in_api(self):
        """API rejects sending OTP or creating account for already registered email."""
        User.objects.create_user(
            username='existing_user',
            email=self.test_email,
            password='TestPassword123!'
        )

        resp = self.client.post(reverse('accounts:api_send_otp'), {
            'identifier': self.test_email,
            'purpose': 'signup'
        }, content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn("already exists", resp.json().get('error', ''))

    @patch('urllib.request.urlopen')
    def test_brevo_api_failure_graceful_handling(self, mock_urlopen):
        """Brevo API HTTP errors (e.g. 401 Unauthorized or 500) are caught gracefully."""
        # Simulate Brevo API HTTP 401 Unauthorized error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url=BrevoEmailProvider.API_URL,
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=MagicMock(read=lambda: b'{"code": "unauthorized", "message": "Key not valid"}')
        )

        with patch.dict('os.environ', {'BREVO_API_KEY': 'invalid-test-key'}):
            success, msg = BrevoEmailProvider.send_otp("test@nearbychat.in", "123456")
            self.assertFalse(success)
            self.assertTrue("failed" in msg.lower() or "error" in msg.lower())

    def test_email_case_and_whitespace_normalization(self):
        """Emails are normalized so whitespace/casing differences resolve to the same identifier."""
        email_raw = "  Alex.Dev@NearbyChat.IN  "
        normalized = VerificationService.normalize_identifier(email_raw)
        self.assertEqual(normalized, "alex.dev@nearbychat.in")
