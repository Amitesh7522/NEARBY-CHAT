"""
Automated tests for the Conversation Rating System.
Validates qualifying chat thresholds, database uniqueness, reputation calculations, and HTTP endpoints.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.core.exceptions import PermissionDenied

from apps.chat.models import Conversation, ConversationParticipant, Message, ConversationRating
from apps.chat.services import ChatService
from apps.accounts.models import Profile

User = get_user_model()

class ConversationRatingTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='alice',
            email='alice@example.com',
            password='TestPassword123!',
            phone_number='9876543201',
            is_verified=True
        )
        self.user2 = User.objects.create_user(
            username='bob',
            email='bob@example.com',
            password='TestPassword123!',
            phone_number='9876543202',
            is_verified=True
        )
        self.user3 = User.objects.create_user(
            username='carol',
            email='carol@example.com',
            password='TestPassword123!',
            phone_number='9876543203',
            is_verified=True
        )

        Profile.objects.get_or_create(user=self.user1, defaults={'display_name': 'Alice'})
        Profile.objects.get_or_create(user=self.user2, defaults={'display_name': 'Bob'})
        Profile.objects.get_or_create(user=self.user3, defaults={'display_name': 'Carol'})

        self.client = Client()

    def test_qualifying_conversation_detection(self):
        """Conversations require at least 2 messages to qualify for rating."""
        # 1. Zero-message conversation
        conv, _ = ChatService.get_or_create_direct_conversation(self.user1, self.user2)
        unrated = ChatService.get_unrated_qualifying_conversation(self.user1, self.user2)
        self.assertIsNone(unrated)

        # 2. One-message conversation
        ChatService.send_message(conv.id, self.user1, "Hello Bob!")
        unrated = ChatService.get_unrated_qualifying_conversation(self.user1, self.user2)
        self.assertIsNone(unrated)

        # 3. Two messages (qualifies!)
        ChatService.send_message(conv.id, self.user2, "Hey Alice, how are you?")
        unrated = ChatService.get_unrated_qualifying_conversation(self.user1, self.user2)
        self.assertIsNotNone(unrated)
        self.assertEqual(unrated.id, conv.id)

    def test_submit_rating_and_prevent_duplicates(self):
        """Enforces one rating per conversation and prevents duplicate submissions."""
        conv, _ = ChatService.get_or_create_direct_conversation(self.user1, self.user2)
        ChatService.send_message(conv.id, self.user1, "Hi Bob!")
        ChatService.send_message(conv.id, self.user2, "Hi Alice!")

        # Alice rates Bob
        rating = ChatService.submit_conversation_rating(
            conversation_id=conv.id,
            rater=self.user1,
            ratee=self.user2,
            score=5,
            tags=['Friendly', 'Interesting']
        )
        self.assertEqual(rating.score, 5)
        self.assertIn('Friendly', rating.tags)
        self.assertIn('Interesting', rating.tags)

        # Alice tries to rate Bob again for same conversation -> ValueError
        with self.assertRaises(ValueError):
            ChatService.submit_conversation_rating(
                conversation_id=conv.id,
                rater=self.user1,
                ratee=self.user2,
                score=4
            )

        # Once rated, conversation is no longer unrated
        unrated = ChatService.get_unrated_qualifying_conversation(self.user1, self.user2)
        self.assertIsNone(unrated)

        # But Bob can still rate Alice for this conversation
        bob_unrated = ChatService.get_unrated_qualifying_conversation(self.user2, self.user1)
        self.assertIsNotNone(bob_unrated)

    def test_public_rating_threshold(self):
        """Averages are only displayed publicly once at least 3 ratings are collected."""
        # 0 ratings
        summary_0 = ChatService.get_user_rating_summary(self.user2)
        self.assertFalse(summary_0['show_public'])
        self.assertTrue(summary_0['is_new_member'])

        # 1 rating from user1
        conv1, _ = ChatService.get_or_create_direct_conversation(self.user1, self.user2)
        ChatService.send_message(conv1.id, self.user1, "Msg 1")
        ChatService.send_message(conv1.id, self.user2, "Msg 2")
        ChatService.submit_conversation_rating(conv1.id, self.user1, self.user2, 5, ['Friendly'])

        summary_1 = ChatService.get_user_rating_summary(self.user2)
        self.assertFalse(summary_1['show_public'])
        self.assertTrue(summary_1['is_new_member'])

        # 2 ratings (user3 in another conversation)
        conv2, _ = ChatService.get_or_create_direct_conversation(self.user3, self.user2)
        ChatService.send_message(conv2.id, self.user3, "Msg 1")
        ChatService.send_message(conv2.id, self.user2, "Msg 2")
        ChatService.submit_conversation_rating(conv2.id, self.user3, self.user2, 4, ['Friendly', 'Respectful'])

        summary_2 = ChatService.get_user_rating_summary(self.user2)
        self.assertFalse(summary_2['show_public'])

        # 3rd rating from user4
        user4 = User.objects.create_user(username='dave', email='dave@example.com', password='TestPassword123!')
        conv3, _ = ChatService.get_or_create_direct_conversation(user4, self.user2)
        ChatService.send_message(conv3.id, user4, "Msg 1")
        ChatService.send_message(conv3.id, self.user2, "Msg 2")
        ChatService.submit_conversation_rating(conv3.id, user4, self.user2, 5, ['Friendly', 'Good conversation'])

        # Threshold (3 ratings) met! (5 + 4 + 5) / 3 = 4.67 -> 4.7
        summary_3 = ChatService.get_user_rating_summary(self.user2)
        self.assertTrue(summary_3['show_public'])
        self.assertEqual(summary_3['rating_count'], 3)
        self.assertEqual(summary_3['average_score'], 4.7)
        self.assertEqual(summary_3['top_tags'][0], 'Friendly')

    def test_http_rating_endpoint_ajax(self):
        """Tests the POST /chats/rate/ endpoint with AJAX request."""
        self.client.force_login(self.user1)

        conv, _ = ChatService.get_or_create_direct_conversation(self.user1, self.user2)
        ChatService.send_message(conv.id, self.user1, "Msg 1")
        ChatService.send_message(conv.id, self.user2, "Msg 2")

        response = self.client.post(
            '/chats/rate/',
            {
                'conversation_id': str(conv.id),
                'target_username': self.user2.username,
                'score': '5',
                'tags': ['Friendly', 'Interesting']
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        # Confirm rating exists in database
        self.assertTrue(ConversationRating.objects.filter(conversation=conv, rater=self.user1, ratee=self.user2).exists())
