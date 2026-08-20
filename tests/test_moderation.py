"""
Automated tests for the Real-Time Content Moderation and Abusive Word/Short-Form Filter.
Validates English, Hinglish, acronyms, leetspeak, false-positive protection, and chat/room message blocking.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied

from apps.safety.services import ContentModerationService
from apps.chat.services import ChatService
from apps.rooms.services import RoomService
from apps.rooms.models import Room, RoomMember
from apps.accounts.models import Profile

User = get_user_model()

class ContentModerationTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='rohit',
            email='rohit@example.com',
            password='TestPassword123!',
            phone_number='9876543201',
            is_verified=True
        )
        self.user2 = User.objects.create_user(
            username='simran',
            email='simran@example.com',
            password='TestPassword123!',
            phone_number='9876543202',
            is_verified=True
        )
        Profile.objects.get_or_create(user=self.user1, defaults={'display_name': 'Rohit'})
        Profile.objects.get_or_create(user=self.user2, defaults={'display_name': 'Simran'})

    def test_english_profanities_detected(self):
        """Standard English profanities and slurs are detected."""
        offensive_samples = [
            "What the fuck is this?",
            "You are such a bitch",
            "Stop being an asshole",
            "Get out you bastard",
            "Shut up motherfucker",
        ]
        for text in offensive_samples:
            is_abusive, match = ContentModerationService.contains_abusive_content(text)
            self.assertTrue(is_abusive, f"Failed to detect profanity in: '{text}'")

    def test_hinglish_slurs_and_acronyms_detected(self):
        """Hinglish, Hindi romanized abuses, and short forms are detected."""
        offensive_samples = [
            "kya kar raha hai bc",
            "tu mc hai kya",
            "chal nikal bkl",
            "kya haal hai bsdk",
            "tu bada chutiya hai",
            "saale madarchod",
            "bhosdike chup kar",
            "gandu insan",
            "chal be harami",
        ]
        for text in offensive_samples:
            is_abusive, match = ContentModerationService.contains_abusive_content(text)
            self.assertTrue(is_abusive, f"Failed to detect Hinglish abuse in: '{text}'")

    def test_toxic_acronyms_and_shortforms_detected(self):
        """Toxic short forms like stfu, gtfo, mfer are detected."""
        acronym_samples = [
            "just stfu already",
            "gtfo of here",
            "you dumb mfer",
            "what the fck",
        ]
        for text in acronym_samples:
            is_abusive, match = ContentModerationService.contains_abusive_content(text)
            self.assertTrue(is_abusive, f"Failed to detect acronym abuse in: '{text}'")

    def test_spaced_and_punctuated_abbreviations_detected(self):
        """Detects spaced and punctuated bypass attempts (e.g. 'b c', 'b.c', 'b.k.l', 'f u c k')."""
        obfuscated_samples = [
            "tere ko b c bolu",
            "ye m.c kya kar raha hai",
            "tu b.k.l hai",
            "f u c k this",
            "s.t.f.u now",
        ]
        for text in obfuscated_samples:
            is_abusive, match = ContentModerationService.contains_abusive_content(text)
            self.assertTrue(is_abusive, f"Failed to detect punctuated/spaced abuse in: '{text}'")

    def test_leetspeak_and_repeated_characters_detected(self):
        """Detects symbol substitutions and repeated character variations (e.g. 'f*ck', 'b!tch', 'fuuuuck', 'bcccc')."""
        leetspeak_samples = [
            "f*ck you",
            "b!tch please",
            "fuuuuck off",
            "tu bcccc",
        ]
        for text in leetspeak_samples:
            is_abusive, match = ContentModerationService.contains_abusive_content(text)
            self.assertTrue(is_abusive, f"Failed to detect leetspeak abuse in: '{text}'")

    def test_benign_words_false_positive_protection(self):
        """Ensures benign everyday words with matching substrings are NOT falsely blocked."""
        benign_samples = [
            "Welcome to the physics class",
            "I assume you know the answer",
            "Please pass me the book",
            "We use a compass for navigation",
            "I am late because of traffic",
            "Would you like a biscuit?",
            "Check the document details",
            "Read this passage carefully",
            "The classic car looks great",
            "We had a glass of juice",
        ]
        for text in benign_samples:
            is_abusive, match = ContentModerationService.contains_abusive_content(text)
            self.assertFalse(is_abusive, f"Falsely flagged benign text: '{text}' (matched: '{match}')")

    def test_mask_abusive_content(self):
        """Replaces abusive words with asterisks."""
        text = "Hello you bitch and asshole"
        masked = ContentModerationService.mask_abusive_content(text)
        self.assertNotIn("bitch", masked)
        self.assertNotIn("asshole", masked)
        self.assertIn("Hello you", masked)

    def test_chat_send_message_blocks_abusive_language(self):
        """ChatService.send_message raises ValidationError on abusive content."""
        conv, _ = ChatService.get_or_create_direct_conversation(self.user1, self.user2)

        # 1. Clean message succeeds
        msg = ChatService.send_message(conv.id, self.user1, "Hey Simran, how are you?")
        self.assertIsNotNone(msg)

        # 2. Abusive message raises ValidationError
        with self.assertRaises(ValidationError):
            ChatService.send_message(conv.id, self.user1, "Hey you bkl madarchod")

    def test_room_send_message_blocks_abusive_language(self):
        """RoomService.send_room_message raises ValidationError on abusive content."""
        room = Room.objects.create(name="Tech Talk", slug="tech-talk", creator=self.user1)
        RoomMember.objects.create(room=room, user=self.user1, role='member')

        # 1. Clean message succeeds
        msg = RoomService.send_room_message(room.id, self.user1, "Hello everyone in the room!")
        self.assertIsNotNone(msg)

        # 2. Abusive message raises ValidationError
        with self.assertRaises(ValidationError):
            RoomService.send_room_message(room.id, self.user1, "stfu all of you")
