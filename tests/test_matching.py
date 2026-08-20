from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.matching.services import MatchmakingService
from apps.matching.models import MatchQueue
from apps.safety.models import Block

User = get_user_model()

class MatchmakingTestCase(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='player1', email='p1@example.com', password='Password123!')
        self.user2 = User.objects.create_user(username='player2', email='p2@example.com', password='Password123!')
        self.user3 = User.objects.create_user(username='player3', email='p3@example.com', password='Password123!')

    def test_enqueue_and_atomic_pairing(self):
        """User 1 enqueues, User 2 joins and an atomic match is formed."""
        # 1. User 1 enqueues
        res1 = MatchmakingService.find_or_enqueue(self.user1, 'channel_user1')
        self.assertFalse(res1['matched'])
        self.assertEqual(MatchQueue.objects.filter(user=self.user1).count(), 1)

        # 2. User 2 enqueues -> triggers instant atomic match
        res2 = MatchmakingService.find_or_enqueue(self.user2, 'channel_user2')
        self.assertTrue(res2['matched'])
        self.assertIsNotNone(res2['conversation_id'])
        self.assertEqual(res2['user1_channel'], 'channel_user2')
        self.assertEqual(res2['user2_channel'], 'channel_user1')

        # Both users should be removed from waiting queue
        self.assertEqual(MatchQueue.objects.filter(status='waiting').count(), 0)

    def test_cancel_queue(self):
        """Cancelling queue removes user entry."""
        MatchmakingService.find_or_enqueue(self.user1, 'channel_user1')
        self.assertEqual(MatchQueue.objects.filter(user=self.user1).count(), 1)

        MatchmakingService.cancel_queue(self.user1)
        self.assertEqual(MatchQueue.objects.filter(user=self.user1).count(), 0)

    def test_blocked_users_never_matched(self):
        """If User 1 has blocked User 2, matchmaking will not pair them."""
        Block.objects.create(blocker=self.user1, blocked=self.user2)

        # User 1 enqueues
        MatchmakingService.find_or_enqueue(self.user1, 'channel_user1')

        # User 2 enqueues -> Should NOT match with User 1, but rather enqueue User 2
        res2 = MatchmakingService.find_or_enqueue(self.user2, 'channel_user2')
        self.assertFalse(res2['matched'])
        self.assertEqual(MatchQueue.objects.filter(status='waiting').count(), 2)

    def test_existing_chat_partner_strictly_never_matched(self):
        """Users who already have an existing chat are strictly never matched in Random Chat."""
        from apps.chat.services import ChatService
        # Create an existing conversation between user1 and user2
        ChatService.get_or_create_direct_conversation(self.user1, self.user2)

        # User 1 enqueues
        res1 = MatchmakingService.find_or_enqueue(self.user1, 'channel_user1')
        self.assertFalse(res1['matched'])

        # User 2 enqueues -> Should NOT match with user1 because they already have a chat
        res2 = MatchmakingService.find_or_enqueue(self.user2, 'channel_user2')
        self.assertFalse(res2['matched'])
        self.assertEqual(MatchQueue.objects.filter(status='waiting').count(), 2)

        # User 3 (a new stranger) enqueues -> Matches with User 1 (first in queue)
        res3 = MatchmakingService.find_or_enqueue(self.user3, 'channel_user3')
        self.assertTrue(res3['matched'])
        self.assertEqual(res3['user2_name'], self.user1.username)
