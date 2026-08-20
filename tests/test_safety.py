from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from apps.safety.models import Block, Report
from apps.safety.services import SafetyService

User = get_user_model()

class SafetyTestCase(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='safe_user', email='safe@example.com', password='Password123!')
        self.user2 = User.objects.create_user(username='abusive_user', email='abuse@example.com', password='Password123!')

    def test_blocking_and_unblocking(self):
        """User can block and unblock another user."""
        block, created = SafetyService.block_user(self.user1, self.user2)
        self.assertTrue(created)
        self.assertTrue(Block.objects.filter(blocker=self.user1, blocked=self.user2).exists())

        # Unblock
        unblocked = SafetyService.unblock_user(self.user1, self.user2)
        self.assertTrue(unblocked)
        self.assertFalse(Block.objects.filter(blocker=self.user1, blocked=self.user2).exists())

    def test_self_block_prohibited(self):
        """User cannot block themselves."""
        with self.assertRaises(ValidationError):
            SafetyService.block_user(self.user1, self.user1)

    def test_incident_reporting(self):
        """Users can submit reports on abusive users."""
        report = SafetyService.file_report(
            reporter=self.user1,
            reported_user=self.user2,
            reason='harassment',
            details='Sent inappropriate language.'
        )
        self.assertIsNotNone(report.id)
        self.assertEqual(report.status, 'pending')
        self.assertEqual(report.reason, 'harassment')
