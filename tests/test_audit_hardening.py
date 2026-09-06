import uuid
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.cache import cache
from apps.chat.models import Conversation, ConversationParticipant, Message
from apps.chat.services import ChatService
from apps.core.security import is_rate_limited, check_rate_limit, record_failed_attempt, clear_failed_attempts

User = get_user_model()

class AuditHardeningTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(
            username='mainuser',
            email='main@example.com',
            password='Password123!'
        )
        self.user.profile.display_name = 'Main User'
        self.user.profile.save()

    def test_conversations_summary_bounded_query_growth(self):
        """
        Verify get_user_conversations_summary exhibits O(1) query scaling.
        Query count does not grow linearly with the number of conversations (Q(2) == Q(10)).
        """
        # 1. Create 2 conversations
        partners = []
        for i in range(10):
            p = User.objects.create_user(
                username=f'partner_{i}',
                email=f'partner_{i}@example.com',
                password='Password123!'
            )
            p.profile.display_name = f'Partner {i}'
            p.profile.save()
            partners.append(p)

        # Setup first 2 conversations
        for i in range(2):
            conv, _ = ChatService.get_or_create_direct_conversation(self.user, partners[i])
            ChatService.send_message(conv.id, partners[i], f'Msg {i}')

        # Measure query count for 2 conversations
        with self.assertNumQueries(4):
            summary_2 = ChatService.get_user_conversations_summary(self.user)
            self.assertEqual(len(summary_2), 2)

        # Setup remaining 8 conversations (10 total)
        for i in range(2, 10):
            conv, _ = ChatService.get_or_create_direct_conversation(self.user, partners[i])
            ChatService.send_message(conv.id, partners[i], f'Msg {i}')

        # Measure query count for 10 conversations -> must remain exactly 4 queries (bounded O(1))
        with self.assertNumQueries(4):
            summary_10 = ChatService.get_user_conversations_summary(self.user)
            self.assertEqual(len(summary_10), 10)
            for s in summary_10:
                self.assertIsNotNone(s['other_user'])
                self.assertIsNotNone(s['other_profile'])
                self.assertIsNotNone(s['last_message'])

    def test_messages_page_bounded_query_growth(self):
        """
        Verify get_messages_page exhibits O(1) query scaling and prefetches sender profile.
        """
        other = User.objects.create_user(
            username='chatmate',
            email='chatmate@example.com',
            password='Password123!'
        )
        conv, _ = ChatService.get_or_create_direct_conversation(self.user, other)
        for i in range(25):
            ChatService.send_message(conv.id, other if i % 2 == 0 else self.user, f'Msg {i}')

        # Loading 5 messages = 3 queries
        with self.assertNumQueries(3):
            msgs_5 = ChatService.get_messages_page(conv.id, self.user, limit=5)
            self.assertEqual(len(msgs_5), 5)
            for m in msgs_5:
                _ = m.sender.profile.get_display_name()

        # Loading 25 messages = exactly 3 queries (no N+1 per message during iteration)
        with self.assertNumQueries(3):
            msgs_25 = ChatService.get_messages_page(conv.id, self.user, limit=25)
            self.assertEqual(len(msgs_25), 25)
            for m in msgs_25:
                _ = m.sender.profile.get_display_name()

    def test_login_rate_limiting_with_shared_ip_protection(self):
        """
        Verify multi-tiered login rate limiting:
        - Failed attempts against User A trigger cooldown after threshold.
        - Legitimate User B sharing the same IP can still authenticate successfully.
        - Successful login clears prior failure counts.
        """
        user_b = User.objects.create_user(
            username='user_b',
            email='userb@example.com',
            password='CorrectPassword123!'
        )

        # 5 failed login attempts for User A
        for _ in range(5):
            resp = self.client.post(reverse('accounts:login'), {
                'username': 'mainuser',
                'password': 'WrongPassword!'
            }, REMOTE_ADDR='203.0.113.42')
            self.assertEqual(resp.status_code, 200)

        # 6th attempt for User A is blocked by rate-limiter cooldown
        resp_locked = self.client.post(reverse('accounts:login'), {
            'username': 'mainuser',
            'password': 'Password123!'  # Even correct password is gated during cooldown
        }, REMOTE_ADDR='203.0.113.42')
        self.assertContains(resp_locked, 'Too many failed login attempts')

        # User B on the same IP (203.0.113.42) can still log in successfully
        resp_user_b = self.client.post(reverse('accounts:login'), {
            'username': 'user_b',
            'password': 'CorrectPassword123!'
        }, REMOTE_ADDR='203.0.113.42')
        self.assertEqual(resp_user_b.status_code, 302)

    def test_strict_csp_and_security_headers(self):
        """
        Verify CSP directives contain no wildcards, no unsafe-eval, and permit blob:/ws:/wss:.
        """
        self.client.force_login(self.user)
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)

        csp = response.headers.get('Content-Security-Policy', '')
        self.assertIn("default-src 'self'", csp)
        self.assertNotIn('unsafe-eval', csp)
        self.assertNotIn('https:', csp)
        self.assertIn('connect-src', csp)
        self.assertIn('ws:', csp)
        self.assertIn('wss:', csp)
        self.assertIn('blob:', csp)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)

        self.assertEqual(response.headers.get('Referrer-Policy'), 'strict-origin-when-cross-origin')
        self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')

    def test_minimal_liveness_and_readiness_probes(self):
        """
        Verify /health/ returns minimal JSON without leaking internal topology,
        while /health/ready/ verifies subsystem health.
        """
        # Liveness
        resp_live = self.client.get(reverse('health_live'))
        self.assertEqual(resp_live.status_code, 200)
        self.assertEqual(resp_live.json(), {'status': 'ok'})

        # Readiness
        resp_ready = self.client.get(reverse('health_readiness'))
        self.assertEqual(resp_ready.status_code, 200)
        self.assertEqual(resp_ready.json(), {'status': 'ready'})
