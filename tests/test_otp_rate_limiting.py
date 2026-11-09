from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from django.db import connection, connections, close_old_connections
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import OTPVerification
from apps.accounts.services import BrevoEmailProvider, VerificationService, hash_otp
from apps.core.security import RateLimitBackendUnavailable, consume_atomic_redis_rate_limit


class FakeAtomicRedisCache:
    def __init__(self):
        self.values = {}
        self.timeouts = {}
        self.raise_error = False

    def add(self, key, value, timeout=None):
        if self.raise_error:
            raise ConnectionError('cache unavailable')
        if key in self.values:
            return False
        self.values[key] = value
        self.timeouts[key] = timeout
        return True

    def incr(self, key):
        if self.raise_error:
            raise ConnectionError('cache unavailable')
        if key not in self.values:
            raise ValueError('missing key')
        self.values[key] += 1
        return self.values[key]


class OTPRecipientRateLimitTests(TestCase):
    email = 'rate-limit@example.com'

    @patch.object(BrevoEmailProvider, 'send_otp', return_value=(False, 'Provider rejected request.'))
    def test_failed_brevo_delivery_does_not_consume_recipient_quota(self, mock_send):
        for _ in range(5):
            success, _, cooldown = VerificationService.send_otp_challenge(self.email, ip_address='203.0.113.10')
            self.assertFalse(success)
            self.assertEqual(cooldown, 0)

        self.assertEqual(OTPVerification.objects.filter(identifier=self.email).count(), 0)
        self.assertEqual(mock_send.call_count, 5)

    @patch.object(BrevoEmailProvider, 'send_otp', return_value=(True, 'Sent'))
    def test_five_successful_deliveries_enforce_recipient_limit_with_actual_retry_after(self, mock_send):
        now = timezone.now()
        for minute in (50, 40, 30, 20, 10):
            record = OTPVerification.objects.create(
                identifier=self.email,
                otp_hash=hash_otp(f'1000{minute // 10}'),
                purpose='signup',
                expires_at=now + timedelta(minutes=10),
                is_used=True,
            )
            OTPVerification.objects.filter(pk=record.pk).update(created_at=now - timedelta(minutes=minute))

        success, message, cooldown = VerificationService.send_otp_challenge(self.email, ip_address='203.0.113.10')

        self.assertFalse(success)
        self.assertIn('Too many', message)
        self.assertGreaterEqual(cooldown, 599)
        self.assertLessEqual(cooldown, 601)
        mock_send.assert_not_called()

    @patch.object(BrevoEmailProvider, 'send_otp', return_value=(True, 'Sent'))
    def test_resend_cooldown_is_preserved(self, mock_send):
        success, _, cooldown = VerificationService.send_otp_challenge(self.email, ip_address='203.0.113.10')
        self.assertTrue(success)
        self.assertEqual(cooldown, 60)

        success, message, cooldown = VerificationService.send_otp_challenge(self.email, ip_address='203.0.113.10')
        self.assertFalse(success)
        self.assertIn('Please wait', message)
        self.assertGreaterEqual(cooldown, 1)
        self.assertLessEqual(cooldown, 60)
        self.assertEqual(mock_send.call_count, 1)


class OTPIPRateLimitTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(REDIS_URL='redis://redis.example:6379/0')
    def test_atomic_ip_limiter_counts_repeated_failed_delivery_attempts(self):
        request = self.factory.post('/accounts/api/otp/send/', REMOTE_ADDR='10.0.0.1', HTTP_X_FORWARDED_FOR='203.0.113.50')
        cache = FakeAtomicRedisCache()

        self.assertFalse(consume_atomic_redis_rate_limit(request, 'otp_send_ip', 2, 3600, cache_backend=cache))
        self.assertFalse(consume_atomic_redis_rate_limit(request, 'otp_send_ip', 2, 3600, cache_backend=cache))
        self.assertTrue(consume_atomic_redis_rate_limit(request, 'otp_send_ip', 2, 3600, cache_backend=cache))
        self.assertEqual(cache.timeouts['nc_rl_otp_send_ip_203.0.113.50'], 3600)

    @override_settings(REDIS_URL='redis://redis.example:6379/0')
    def test_redis_errors_fail_closed(self):
        request = self.factory.post('/accounts/api/otp/send/', REMOTE_ADDR='10.0.0.1')
        cache = FakeAtomicRedisCache()
        cache.raise_error = True

        with self.assertRaises(RateLimitBackendUnavailable):
            consume_atomic_redis_rate_limit(request, 'otp_send_ip', 2, 3600, cache_backend=cache)

    @patch('apps.accounts.views.consume_atomic_redis_rate_limit', side_effect=[False, False, True])
    @patch.object(BrevoEmailProvider, 'send_otp', return_value=(False, 'Provider rejected request.'))
    def test_failed_deliveries_are_limited_by_ip(self, mock_send, mock_ip_limit):
        url = reverse('accounts:api_send_otp')
        payload = {'identifier': 'ip-limit@example.com', 'purpose': 'signup'}

        first = self.client.post(url, payload, content_type='application/json', REMOTE_ADDR='10.0.0.1', HTTP_X_FORWARDED_FOR='203.0.113.51')
        second = self.client.post(url, payload, content_type='application/json', REMOTE_ADDR='10.0.0.1', HTTP_X_FORWARDED_FOR='203.0.113.51')
        third = self.client.post(url, payload, content_type='application/json', REMOTE_ADDR='10.0.0.1', HTTP_X_FORWARDED_FOR='203.0.113.51')

        self.assertEqual(first.status_code, 500)
        self.assertEqual(second.status_code, 500)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(mock_send.call_count, 2)

    @patch('apps.accounts.views.consume_atomic_redis_rate_limit', side_effect=RateLimitBackendUnavailable())
    def test_unavailable_redis_returns_service_unavailable(self, mock_ip_limit):
        response = self.client.post(
            reverse('accounts:api_send_otp'),
            {'identifier': 'redis-error@example.com', 'purpose': 'signup'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()['error'],
            'Verification service is temporarily unavailable. Please try again shortly.',
        )
        self.assertNotIn('cooldown', response.json())


class OTPVerificationBehaviorTests(TransactionTestCase):
    email = 'otp-behavior@example.com'

    @patch.object(BrevoEmailProvider, 'send_otp', return_value=(True, 'Sent'))
    def test_otp_expiry_rejects_expired_codes(self, mock_send):
        success, _, _ = VerificationService.send_otp_challenge(self.email, ip_address='203.0.113.60')
        self.assertTrue(success)

        record = OTPVerification.objects.get(identifier=self.email)
        record.expires_at = timezone.now() - timedelta(minutes=1)
        record.save(update_fields=['expires_at'])

        is_valid, message = VerificationService.verify_otp_challenge(self.email, '000000', purpose='signup')
        self.assertFalse(is_valid)
        self.assertIn('expired', message.lower())

    @patch.object(BrevoEmailProvider, 'send_otp', return_value=(True, 'Sent'))
    def test_resend_cooldown_enforces_60_second_wait(self, mock_send):
        first = VerificationService.send_otp_challenge(self.email, ip_address='203.0.113.61')
        self.assertTrue(first[0])
        self.assertEqual(first[2], 60)

        second = VerificationService.send_otp_challenge(self.email, ip_address='203.0.113.61')
        self.assertFalse(second[0])
        self.assertIn('Please wait', second[1])
        self.assertGreaterEqual(second[2], 1)
        self.assertLessEqual(second[2], 60)

    @patch.object(BrevoEmailProvider, 'send_otp', return_value=(True, 'Sent'))
    def test_verify_otp_rejects_after_five_incorrect_attempts(self, mock_send):
        success, _, _ = VerificationService.send_otp_challenge(self.email, ip_address='203.0.113.62')
        self.assertTrue(success)

        record = OTPVerification.objects.get(identifier=self.email)
        for attempt in range(1, 5):
            is_valid, message = VerificationService.verify_otp_challenge(self.email, '000000', purpose='signup')
            self.assertFalse(is_valid)
            if attempt < 5:
                self.assertIn(f'{5 - attempt} attempt', message)

        is_valid, message = VerificationService.verify_otp_challenge(self.email, '000000', purpose='signup')
        self.assertFalse(is_valid)
        self.assertIn('Too many failed attempts', message)
        record.refresh_from_db()
        self.assertTrue(record.is_used)

    def test_concurrent_verification_attempts_only_allow_one_success(self):
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL row locking is exercised in production')

        otp = '123456'
        OTPVerification.objects.create(
            identifier=self.email,
            otp_hash=hash_otp(otp),
            purpose='signup',
            expires_at=timezone.now() + timedelta(minutes=10),
            is_used=False,
            attempts=0,
        )

        with patch.object(OTPVerification.objects, 'select_for_update', wraps=OTPVerification.objects.select_for_update) as mock_lock:
            with ThreadPoolExecutor(max_workers=8) as executor:
                def verify_worker(_):
                    close_old_connections()
                    try:
                        return VerificationService.verify_otp_challenge(self.email, otp, purpose='signup')
                    finally:
                        connections['default'].close()

                results = list(executor.map(verify_worker, range(8)))

        close_old_connections()
        self.assertTrue(mock_lock.called)
        self.assertEqual(sum(1 for ok, _ in results if ok), 1)


class OTPRecipientConcurrencyTests(TransactionTestCase):
    email = 'concurrent-rate-limit@example.com'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider_patch = patch.object(BrevoEmailProvider, 'send_otp', return_value=(True, 'Sent'))
        cls.provider_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.provider_patch.stop()
        super().tearDownClass()

    def test_concurrent_requests_do_not_exceed_recipient_limit(self):
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL advisory locking is exercised in production')

        def send(purpose):
            close_old_connections()
            try:
                return VerificationService.send_otp_challenge(
                    self.email,
                    purpose=purpose,
                    ip_address='203.0.113.52',
                )[0]
            finally:
                connections['default'].close()

        with ThreadPoolExecutor(max_workers=8) as executor:
            outcomes = list(executor.map(send, [f'concurrency-{index}' for index in range(8)]))

        self.assertEqual(sum(outcomes), VerificationService.OTP_HOURLY_LIMIT)
        self.assertEqual(OTPVerification.objects.filter(identifier=self.email).count(), VerificationService.OTP_HOURLY_LIMIT)
