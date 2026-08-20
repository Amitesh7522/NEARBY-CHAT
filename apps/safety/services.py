"""
Safety and Content Moderation Services.
Provides automated detection, filtering, and rejection of abusive language,
profanities, toxic short forms, and regional/Hinglish slurs.
"""
import re
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import Block, Report

class ContentModerationService:
    """
    Intelligent multi-language content moderation engine.
    Detects and filters abusive terms, profanities, toxic acronyms, and leetspeak
    while strictly protecting benign words (e.g., class, assume, because, document).
    """

    # Exact word-boundary patterns (English & Hinglish slurs/abuses)
    EXACT_BLOCKED_WORDS = [
        # English primary profanities & slurs
        r'fuck(?:er|ing|ed|s|off)?',
        r'motherfuck(?:er|ing|s)?',
        r'bitch(?:es|y)?',
        r'bastard(?:s)?',
        r'asshole(?:s)?',
        r'bullshit',
        r'cunt(?:s)?',
        r'pussy(?:ies)?',
        r'whore(?:s)?',
        r'slut(?:s)?',
        r'nigger(?:s)?',
        r'faggot(?:s)?',
        r'twat(?:s)?',
        r'wanker(?:s)?',
        r'prick(?:s)?',

        # English short forms & acronyms
        r'stfu',
        r'gtfo',
        r'fck',
        r'fuk',
        r'mfer',

        # Hinglish & Hindi romanized abuses & compound slurs
        r'madarchod(?:s|e)?',
        r'maderchod(?:s|e)?',
        r'madarjaat',
        r'behenchod(?:s|e)?',
        r'bhenchod(?:s|e)?',
        r'bhosdike',
        r'bhosad(?:i|pappu)?',
        r'bhosada',
        r'chutiya(?:s|e|on)?',
        r'chutya(?:s|e)?',
        r'choot(?:iye|iya)?',
        r'gandu(?:s)?',
        r'gaand(?:u|masti)?',
        r'lauda(?:s)?',
        r'loda(?:s)?',
        r'lavda(?:s)?',
        r'lund(?:s)?',
        r'randi(?:s|baaz)?',
        r'raand',
        r'chinal',
        r'jhant(?:u)?',
        r'harami(?:s)?',
        r'muthal',
        r'chodu',
        r'behenkelode',
        r'tatte',

        # Standalone short forms (e.g. bc, mc, bkl, bsdk, mkc)
        r'bsdk',
        r'b\.s\.d\.k',
        r'bkl',
        r'b\.k\.l',
        r'mkc',
        r'm\.k\.c',
        r'mc',
        r'm\.c',
        r'bc',
        r'b\.c',
    ]

    # Specific separated abbreviations (e.g. 'b c', 'm c', 'b k l', 'm k c', 'b s d k', 'f u c k')
    SEPARATED_ABBREVIATIONS = [
        r'\bb[\s._*-]+c\b',
        r'\bm[\s._*-]+c\b',
        r'\bb[\s._*-]+k[\s._*-]+l\b',
        r'\bm[\s._*-]+k[\s._*-]+c\b',
        r'\bb[\s._*-]+s[\s._*-]+d[\s._*-]+k\b',
        r'\bf[\s._*-]+u[\s._*-]+c[\s._*-]+k\b',
        r'\bs[\s._*-]+t[\s._*-]+f[\s._*-]+u\b',
    ]

    # Standalone single words that need strict word boundary matching
    STRICT_STANDALONE_WORDS = [
        r'\bass\b',
        r'\bdick\b',
        r'\bdicks\b',
        r'\bcock\b',
        r'\bcocks\b',
        r'\btits\b',
    ]

    @classmethod
    def _get_compiled_patterns(cls):
        if not hasattr(cls, '_regex_cache'):
            # Combine exact blocked words with word boundaries
            exact_patterns = [rf'\b{word}\b' for word in cls.EXACT_BLOCKED_WORDS]
            all_patterns = exact_patterns + cls.SEPARATED_ABBREVIATIONS + cls.STRICT_STANDALONE_WORDS
            cls._regex_cache = [re.compile(p, re.IGNORECASE) for p in all_patterns]
        return cls._regex_cache

    @classmethod
    def normalize_text(cls, text: str) -> str:
        """
        Normalizes leetspeak, symbol substitutions, and excessive character repeats.
        Example: 'f*ck' -> 'fuck', 'b!tch' -> 'bitch', 'fuuuuck' -> 'fuck'
        """
        if not text:
            return ""

        # Map common leetspeak substitutions
        substitutions = {
            '@': 'a',
            '4': 'a',
            '$': 's',
            '5': 's',
            '1': 'i',
            '!': 'i',
            '|': 'i',
            '0': 'o',
            '3': 'e',
            '+': 't',
            '7': 't',
            '*': 'u', # Common f*ck mask
        }

        normalized = text.lower()
        for char, repl in substitutions.items():
            normalized = normalized.replace(char, repl)

        # Collapse 3+ repeating characters to 1 (e.g., 'fuuuuuck' -> 'fuck', 'bcccc' -> 'bc')
        normalized = re.sub(r'(.)\1{2,}', r'\1', normalized)
        return normalized

    @classmethod
    def contains_abusive_content(cls, text: str) -> tuple[bool, str]:
        """
        Checks if the provided text contains any abusive language or prohibited short forms.
        Returns (is_abusive, matched_term).
        """
        if not text or not text.strip():
            return False, ""

        raw_text = text.strip()
        normalized_text = cls.normalize_text(raw_text)

        patterns = cls._get_compiled_patterns()

        # Check against both raw text and normalized text
        for pattern in patterns:
            match = pattern.search(raw_text)
            if match:
                return True, match.group(0)

            norm_match = pattern.search(normalized_text)
            if norm_match:
                return True, norm_match.group(0)

        return False, ""

    @classmethod
    def mask_abusive_content(cls, text: str) -> str:
        """
        Replaces detected abusive terms with asterisks (e.g., '****').
        """
        if not text:
            return ""

        masked = text
        patterns = cls._get_compiled_patterns()

        for pattern in patterns:
            masked = pattern.sub(lambda m: '*' * len(m.group(0)), masked)

        return masked

    @classmethod
    def validate_or_reject(cls, text: str):
        """
        Validates message content and raises a user-friendly ValidationError
        if prohibited abusive language or slurs are detected.
        """
        is_abusive, matched = cls.contains_abusive_content(text)
        if is_abusive:
            raise ValidationError(
                _("Message blocked: Please keep conversations respectful and avoid abusive language or slurs.")
            )


class SafetyService:
    @staticmethod
    def block_user(blocker, target_user):
        """Blocks target_user. Fails if user attempts to block themselves."""
        if blocker == target_user:
            raise ValidationError(_("You cannot block yourself."))

        block, created = Block.objects.get_or_create(
            blocker=blocker,
            blocked=target_user
        )
        return block, created

    @staticmethod
    def unblock_user(blocker, target_user):
        """Unblocks target_user."""
        deleted_count, _ = Block.objects.filter(
            blocker=blocker,
            blocked=target_user
        ).delete()
        return deleted_count > 0

    @staticmethod
    def file_report(reporter, reason, details='', reported_user=None, reported_room=None, reported_message=None):
        """Files an incident report for administrative review."""
        if not (reported_user or reported_room or reported_message):
            raise ValidationError(_("A report must be attached to a user, room, or message."))

        report = Report.objects.create(
            reporter=reporter,
            reason=reason,
            details=details,
            reported_user=reported_user,
            reported_room=reported_room,
            reported_message=reported_message,
        )
        return report
