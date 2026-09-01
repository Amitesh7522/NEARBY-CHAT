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

    def test_block_unblock_cycle_preserves_single_conversation_and_messages(self):
        """
        Comprehensive test of block -> unblock -> start chat flow:
        - Exactly ONE conversation exists throughout.
        - Messages are preserved.
        - Chat summary returns only 1 card for the user.
        """
        from django.urls import reverse
        from apps.safety.services import SafetyService

        # 1. Start conversation and send messages
        conv, created = ChatService.get_or_create_direct_conversation(self.user1, self.user2)
        self.assertTrue(created)
        ChatService.send_message(conv.id, self.user1, "Hey Bob, how are you?")
        ChatService.send_message(conv.id, self.user2, "Hey Alice! All good.")
        self.assertEqual(Message.objects.filter(conversation=conv).count(), 2)

        # 2. Block user2
        SafetyService.block_user(self.user1, self.user2)
        self.assertTrue(Block.objects.filter(blocker=self.user1, blocked=self.user2).exists())

        # Verify message send is blocked
        with self.assertRaises(PermissionDenied):
            ChatService.send_message(conv.id, self.user1, "Are you there?")

        # 3. Unblock user2
        SafetyService.unblock_user(self.user1, self.user2)
        self.assertFalse(Block.objects.filter(blocker=self.user1, blocked=self.user2).exists())

        # 4. Open chat again via start_direct_chat_view
        self.client.force_login(self.user1)
        response = self.client.get(reverse('chat:start_direct', kwargs={'username': self.user2.username}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('chat:detail', kwargs={'conversation_id': conv.id}))

        # 5. Verify database integrity
        all_convs_between_pair = ConversationParticipant.objects.filter(
            user=self.user1
        ).values_list('conversation_id', flat=True)
        shared_convs = ConversationParticipant.objects.filter(
            conversation_id__in=all_convs_between_pair,
            user=self.user2
        )
        self.assertEqual(shared_convs.count(), 1, "Must have exactly ONE conversation between pair")
        self.assertEqual(Conversation.objects.count(), 1)

        # Verify messages remain intact
        messages_list = ChatService.get_messages_page(conv.id, self.user1)
        self.assertEqual(len(messages_list), 2)
        self.assertEqual(messages_list[0].content, "Hey Bob, how are you?")
        self.assertEqual(messages_list[1].content, "Hey Alice! All good.")

        # 6. Verify chat summary has exactly 1 entry
        summary = ChatService.get_user_conversations_summary(self.user1)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]['other_user'], self.user2)

    def test_random_to_direct_transition_reuses_conversation(self):
        """If users met via random matching, opening direct chat reuses the existing conversation."""
        from django.urls import reverse
        pair_key = Conversation.get_pair_key(self.user1.id, self.user2.id)
        
        # Initially created via random matching
        rand_conv = Conversation.objects.create(type='random', direct_pair_key=pair_key)
        ConversationParticipant.objects.create(conversation=rand_conv, user=self.user1)
        ConversationParticipant.objects.create(conversation=rand_conv, user=self.user2)
        ChatService.send_message(rand_conv.id, self.user1, "Random match hello!")

        # User1 later clicks 'Message' on User2's profile
        direct_conv, created = ChatService.get_or_create_direct_conversation(self.user1, self.user2)
        self.assertFalse(created, "Must reuse existing conversation, not create a new one")
        self.assertEqual(direct_conv.id, rand_conv.id)
        self.assertEqual(Conversation.objects.count(), 1)

    def test_database_level_pair_key_uniqueness(self):
        """Database uniquely constrains direct_pair_key, preventing duplicate 1-on-1 conversations."""
        from django.db.utils import IntegrityError
        pair_key = Conversation.get_pair_key(self.user1.id, self.user2.id)

        Conversation.objects.create(type='direct', direct_pair_key=pair_key)
        
        with self.assertRaises(IntegrityError):
            Conversation.objects.create(type='direct', direct_pair_key=pair_key)

