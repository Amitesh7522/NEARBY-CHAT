from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from apps.chat.models import Conversation, ConversationParticipant, Message, MessageStatus
from apps.chat.services import ChatService
from apps.safety.models import Block

User = get_user_model()

class ChatTestCase(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='alice', email='alice@example.com', password='Password123!')
        self.user2 = User.objects.create_user(username='bob', email='bob@example.com', password='Password123!')
        self.user3 = User.objects.create_user(username='charlie', email='charlie@example.com', password='Password123!')

    def test_direct_conversation_creation(self):
        """Creates direct conversation between 2 users and prevents duplicate creations."""
        conv1, created1 = ChatService.get_or_create_direct_conversation(self.user1, self.user2)
        self.assertTrue(created1)
        self.assertEqual(conv1.participants.count(), 2)

        # Second call returns existing conversation
        conv2, created2 = ChatService.get_or_create_direct_conversation(self.user1, self.user2)
        self.assertFalse(created2)
        self.assertEqual(conv1.id, conv2.id)

    def test_self_conversation_prohibited(self):
        """User cannot create a direct conversation with themselves."""
        with self.assertRaises(ValueError):
            ChatService.get_or_create_direct_conversation(self.user1, self.user1)

    def test_message_sending_and_idempotency(self):
        """Sending message persists message and ignores duplicate client_msg_id."""
        conv, _ = ChatService.get_or_create_direct_conversation(self.user1, self.user2)
        
        msg1 = ChatService.send_message(
            conversation_id=conv.id,
            sender=self.user1,
            content="Hello Bob!",
            client_msg_id="client_unique_123"
        )
        self.assertEqual(msg1['content'], "Hello Bob!")

        # Duplicate send with same client_msg_id returns existing record
        msg2 = ChatService.send_message(
            conversation_id=conv.id,
            sender=self.user1,
            content="Hello Bob!",
            client_msg_id="client_unique_123"
        )
        self.assertEqual(msg1['id'], msg2['id'])
        self.assertEqual(Message.objects.filter(conversation=conv).count(), 1)

    def test_read_receipts_marking(self):
        """Marking conversation as read updates recipient message statuses."""
        conv, _ = ChatService.get_or_create_direct_conversation(self.user1, self.user2)
        msg = ChatService.send_message(conv.id, self.user1, "Hey Bob", "c1")
        
        status = MessageStatus.objects.get(message_id=msg['id'], user=self.user2)
        self.assertEqual(status.status, 'sent')

        # Bob marks conversation read
        updated_count = ChatService.mark_conversation_read(conv.id, self.user2)
        self.assertEqual(updated_count, 1)

        status.refresh_from_db()
        self.assertEqual(status.status, 'read')

    def test_blocked_user_cannot_chat(self):
        """Blocked users cannot initiate direct chats or send messages."""
        Block.objects.create(blocker=self.user1, blocked=self.user2)
        
        with self.assertRaises(PermissionDenied):
            ChatService.get_or_create_direct_conversation(self.user1, self.user2)

    def test_quick_connect_view(self):
        """Quick connect connects user with an eligible stranger and redirects to chat."""
        from django.urls import reverse
        self.client.force_login(self.user1)

        # First connect: User1 connects with User2 or User3
        res = self.client.get(reverse('chat:quick_connect'))
        self.assertEqual(res.status_code, 302)
        self.assertIn('/chats/', res.url)

        # Verify a conversation was created
        self.assertEqual(Conversation.objects.filter(type='direct').count(), 1)
