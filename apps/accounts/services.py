"""
Authentication and Verification Services.
Provides SMS/OTP service integrations for production providers (MSG91, Fast2SMS, Twilio, AWS SNS)
and development console logger.
"""
import os
import random
import hashlib
import logging
from datetime import timedelta
import urllib.request
import urllib.parse
import json
from django.utils import timezone
from django.conf import settings
from .models import OTPVerification

logger = logging.getLogger(__name__)

import secrets

def generate_secure_otp(length=6) -> str:
    """
    Generate a cryptographically secure numeric OTP string using Python's secrets module.
    """
    return f"{secrets.randbelow(10**length):0{length}d}"

# Alias for backwards compatibility
generate_otp = generate_secure_otp

def hash_otp(otp: str) -> str:
    """
    Hash OTP with Django SECRET_KEY before persisting to database.
    Plaintext OTPs are never stored in the database.
    """
    salt = getattr(settings, 'SECRET_KEY', 'nearby-chat-salt')
    return hashlib.sha256(f"{otp.strip()}:{salt}".encode('utf-8')).hexdigest()

class SMSProviderAdapter:
    """Base SMS Provider Adapter interface."""
    def send_otp(self, phone_number: str, otp: str) -> bool:
        raise NotImplementedError

class ConsoleSMSProvider(SMSProviderAdapter):
    """Development console logger provider."""
    def send_otp(self, phone_number: str, otp: str) -> bool:
        logger.info(f"===> [DEV OTP DISPATCH] Phone: {phone_number} <===")
        return True

class MSG91Provider(SMSProviderAdapter):
    """
    MSG91 India SMS OTP Provider (DLT Compliant).
    Docs: https://msg91.com/help/send-otp
    """
    def __init__(self):
        self.auth_key = os.getenv('MSG91_AUTH_KEY')
        self.template_id = os.getenv('MSG91_TEMPLATE_ID')

    def send_otp(self, phone_number: str, otp: str) -> bool:
        if not self.auth_key or not self.template_id:
            logger.error("MSG91 credentials missing in environment (.env)")
            return False
        
        url = f"https://api.msg91.com/api/v5/otp?template_id={self.template_id}&mobile={phone_number}&authkey={self.auth_key}&otp={otp}"
        try:
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=10) as response:
                res_data = json.loads(response.read().decode())
                return res_data.get('type') == 'success'
        except Exception as e:
            logger.error(f"Failed to dispatch MSG91 OTP: {e}")
            return False

class Fast2SMSProvider(SMSProviderAdapter):
    """
    Fast2SMS India SMS Provider.
    Docs: https://docs.fast2sms.com/
    """
    def __init__(self):
        self.api_key = os.getenv('FAST2SMS_API_KEY')

    def send_otp(self, phone_number: str, otp: str) -> bool:
        if not self.api_key:
            logger.error("Fast2SMS API key missing in environment (.env)")
            return False
        
        # Clean 10-digit number for Indian mobile numbers
        clean_num = phone_number.replace('+91', '').replace('-', '').replace(' ', '')
        url = "https://www.fast2sms.com/dev/bulkV2"
        data = urllib.parse.urlencode({
            'authorization': self.api_key,
            'variables_values': otp,
            'route': 'otp',
            'numbers': clean_num,
        }).encode('utf-8')
        
        try:
            req = urllib.request.Request(url, data=data, method='POST')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            with urllib.request.urlopen(req, timeout=10) as response:
                res_data = json.loads(response.read().decode())
                return res_data.get('return', False)
        except Exception as e:
            logger.error(f"Failed to dispatch Fast2SMS OTP: {e}")
            return False

class TwilioProvider(SMSProviderAdapter):
    """
    Twilio Global SMS Provider.
    Docs: https://www.twilio.com/docs/sms/api
    """
    def __init__(self):
        self.account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.from_number = os.getenv('TWILIO_PHONE_NUMBER')

    def send_otp(self, phone_number: str, otp: str) -> bool:
        if not self.account_sid or not self.auth_token or not self.from_number:
            logger.error("Twilio credentials missing in environment (.env)")
            return False
        
        import base64
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        data = urllib.parse.urlencode({
            'From': self.from_number,
            'To': phone_number,
            'Body': f"Your Nearby Chat verification code is: {otp}. Valid for 10 minutes."
        }).encode('utf-8')

        try:
            auth_str = f"{self.account_sid}:{self.auth_token}"
            b64_auth = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')
            req = urllib.request.Request(url, data=data, method='POST')
            req.add_header('Authorization', f"Basic {b64_auth}")
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status in (200, 201)
        except Exception as e:
            logger.error(f"Failed to dispatch Twilio OTP: {e}")
            return False

class BrevoEmailProvider:
    """
    Production Brevo REST API v3 Integration (https://api.brevo.com/v3/smtp/email).
    Sends transactional emails from verified sender: Nearby Chat <no-reply@nearbychat.in>.
    Never exposes API keys or plaintext tokens in frontend/responses.
    """
    API_URL = "https://api.brevo.com/v3/smtp/email"

    @classmethod
    def send_otp(cls, email_address: str, otp: str) -> tuple[bool, str]:
        from django.template.loader import render_to_string

        api_key = os.getenv('BREVO_API_KEY')
        sender_email = os.getenv('BREVO_SENDER_EMAIL', 'no-reply@nearbychat.in')
        sender_name = os.getenv('BREVO_SENDER_NAME', 'Nearby Chat')

        if not api_key:
            logger.error("BREVO_API_KEY is not configured in the environment (.env).")
            return False, "Email verification service is temporarily unavailable. Please check system configuration."

        subject = f"Your Nearby Chat Verification Code: {otp}"
        
        context = {
            'otp': otp,
            'email': email_address,
            'sender_email': sender_email,
        }

        try:
            html_content = render_to_string('emails/otp_verification.html', context)
        except Exception:
            html_content = f"""<div style="font-family:sans-serif;padding:24px;background:#111827;color:#fff;border-radius:12px;">
                <h2>Nearby<span style="color:#6366f1;">Chat</span></h2>
                <p>Your verification code is:</p>
                <h1 style="letter-spacing:6px;color:#6366f1;">{otp}</h1>
                <p>Valid for 10 minutes. Please do not share this code with anyone.</p>
            </div>"""

        plain_content = (
            f"Your Nearby Chat verification code is: {otp}\n\n"
            f"This code is valid for 10 minutes.\n\n"
            f"Team Nearby Chat ({sender_email})"
        )

        payload = {
            "sender": {
                "name": sender_name,
                "email": sender_email
            },
            "to": [
                {
                    "email": email_address
                }
            ],
            "subject": subject,
            "htmlContent": html_content,
            "textContent": plain_content
        }

        headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        try:
            data_bytes = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(cls.API_URL, data=data_bytes, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=12) as response:
                res_body = response.read().decode('utf-8')
                res_json = json.loads(res_body) if res_body else {}
                message_id = res_json.get('messageId', 'unknown')
                
                if response.status in (200, 201, 202):
                    logger.info(f"Brevo email OTP accepted: status={response.status}, messageId={message_id}")
                    return True, "Verification code sent to your email."
                logger.error(f"Brevo API unexpected status: status={response.status}, body={res_body}")
                return False, "Failed to deliver email through Brevo API."
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode('utf-8')
                logger.error(f"Brevo API HTTP error: status={e.code}, body={err_body}")
            except Exception:
                logger.error(f"Brevo API HTTP error: status={e.code}")
            if e.code == 401:
                return False, "Email provider authentication failed. Please check BREVO_API_KEY."
            elif e.code == 400:
                return False, "Invalid email request rejected by provider."
            return False, "Email delivery provider encountered an error. Please try again."
        except Exception as e:
            logger.error(f"Brevo API network failure: {e}")
            return False, "Unable to reach email service. Please try again."

# Alias for backwards compatibility
EmailVerificationProvider = BrevoEmailProvider

def get_sms_provider() -> SMSProviderAdapter:
    """Factory returning configured SMS provider."""
    provider_name = os.getenv('OTP_PROVIDER', 'console').lower()
    if provider_name == 'msg91':
        return MSG91Provider()
    elif provider_name == 'fast2sms':
        return Fast2SMSProvider()
    elif provider_name == 'twilio':
        return TwilioProvider()
    return ConsoleSMSProvider()

class VerificationService:
    @staticmethod
    def normalize_identifier(identifier: str) -> str:
        """Normalizes email or phone number for consistent hashing and lookup."""
        ident = identifier.strip()
        if '@' in ident:
            return ident.lower()
        # Phone: extract last 10 digits
        clean_digits = ''.join(c for c in ident if c.isdigit())
        if len(clean_digits) >= 10:
            return clean_digits[-10:]
        return clean_digits

    @staticmethod
    def send_otp_challenge(identifier: str, purpose: str = 'signup', ip_address: str = None) -> tuple[bool, str, int]:
        """
        Creates an OTP challenge, enforces rate limits, resend cooldown, and dispatches
        via Brevo API (for email) or SMS Provider (for phone).
        Returns: (success: bool, message: str, cooldown_seconds: int)
        """
        norm_ident = VerificationService.normalize_identifier(identifier)
        if not norm_ident:
            return False, "A valid email address or phone number is required.", 0

        now = timezone.now()

        # 1. Check Rate Limiting (Max 5 requests per hour per identifier)
        one_hour_ago = now - timedelta(hours=1)
        recent_requests_count = OTPVerification.objects.filter(
            identifier=norm_ident,
            created_at__gte=one_hour_ago
        ).count()

        if recent_requests_count >= 5:
            return False, "Too many verification requests. Please wait an hour before requesting again.", 3600

        # 2. Check 60-Second Resend Cooldown
        latest_otp = OTPVerification.objects.filter(
            identifier=norm_ident,
            purpose=purpose,
            is_used=False
        ).order_by('-created_at').first()

        if latest_otp and (now - latest_otp.created_at).total_seconds() < 60:
            remaining_cooldown = int(60 - (now - latest_otp.created_at).total_seconds())
            return False, f"Please wait {remaining_cooldown} seconds before requesting a new code.", remaining_cooldown

        # 3. Invalidate prior unused OTPs for this identifier & purpose
        OTPVerification.objects.filter(
            identifier=norm_ident,
            purpose=purpose,
            is_used=False
        ).update(is_used=True)

        # 4. Generate cryptographically secure OTP and hash it
        otp = generate_secure_otp(6)
        hashed = hash_otp(otp)
        expires_at = now + timedelta(minutes=10)

        record = OTPVerification.objects.create(
            identifier=norm_ident,
            otp_hash=hashed,
            purpose=purpose,
            expires_at=expires_at,
            ip_address=ip_address,
            last_resend_at=now,
        )

        # 5. Dispatch through Brevo API (for email) or SMS provider (for phone)
        if '@' in norm_ident:
            success, msg = BrevoEmailProvider.send_otp(norm_ident, otp)
        else:
            provider = get_sms_provider()
            dispatched = provider.send_otp(norm_ident, otp)
            if dispatched:
                success, msg = True, "Verification code sent via SMS."
            else:
                success, msg = False, "Failed to send SMS verification code."

        if success:
            return True, msg, 60
        else:
            # Clean up failed dispatch record
            record.is_used = True
            record.save(update_fields=['is_used'])
            return False, msg, 0

    @staticmethod
    def verify_otp_challenge(identifier: str, otp: str, purpose: str = 'signup') -> tuple[bool, str]:
        """
        Verifies supplied OTP against stored hashed record.
        Enforces 5 maximum failed attempts and expiration.
        Returns: (success: bool, message: str)
        """
        norm_ident = VerificationService.normalize_identifier(identifier)
        if not norm_ident or not otp:
            return False, "Verification code and email/phone are required."

        record = OTPVerification.objects.filter(
            identifier=norm_ident,
            purpose=purpose,
            is_used=False
        ).order_by('-created_at').first()

        if not record:
            return False, "Invalid or expired verification code. Please request a new one."

        if timezone.now() >= record.expires_at:
            record.is_used = True
            record.save(update_fields=['is_used'])
            return False, "Verification code has expired. Please request a new one."

        if record.attempts >= 5:
            record.is_used = True
            record.save(update_fields=['is_used'])
            return False, "Too many failed attempts. This code has been invalidated. Please request a new one."

        # Increment attempt counter
        record.attempts += 1

        # Check cryptographic hash match
        if record.otp_hash == hash_otp(otp):
            record.is_used = True
            record.save(update_fields=['attempts', 'is_used'])
            return True, "Verification successful."
        else:
            remaining_attempts = 5 - record.attempts
            if remaining_attempts <= 0:
                record.is_used = True
                record.save(update_fields=['attempts', 'is_used'])
                return False, "Too many failed attempts. This code has been invalidated. Please request a new one."
            
            record.save(update_fields=['attempts'])
            return False, f"Incorrect verification code. {remaining_attempts} attempt(s) remaining."


class ReferralService:
    @staticmethod
    def get_or_create_invite_code(user):
        """Returns or ensures user has an active invite code."""
        if hasattr(user, 'profile'):
            if not user.profile.invite_code:
                user.profile.save()
            return user.profile.invite_code
        return ''

    @staticmethod
    def record_referral(invite_code, referred_user, ip_address=None):
        """
        Associates an invite code with a newly registered user.
        Strictly prevents self-referrals and duplicate claims.
        """
        if not invite_code or not referred_user or not referred_user.is_authenticated:
            return None

        invite_code = str(invite_code).strip().upper()

        from .models import Profile, Referral
        inviter_profile = Profile.objects.filter(invite_code__iexact=invite_code).select_related('user').first()
        if not inviter_profile:
            return None

        inviter = inviter_profile.user

        # Anti-abuse: Self-referral prevention
        if inviter == referred_user:
            logger.warning(f"Prevented self-referral attempt for user {referred_user.username}")
            return None

        # Anti-abuse: Duplicate referral check (referred_user already attributed)
        if Referral.objects.filter(referred_user=referred_user).exists():
            return None

        try:
            referral = Referral.objects.create(
                inviter=inviter,
                referred_user=referred_user,
                invite_code=invite_code,
                status='pending',
                ip_address=ip_address
            )
            # Check if newly created user already meets any immediate qualification criteria
            ReferralService.check_and_qualify_referral(referred_user)
            return referral
        except Exception as e:
            logger.error(f"Error creating referral: {e}")
            return None

    @staticmethod
    def check_and_qualify_referral(user):
        """
        Evaluates whether user's referral should transition from pending -> qualified.
        Qualifying condition: user has sent at least 1 message OR joined 1 room OR has profile content.
        """
        if not user or not user.is_authenticated:
            return False

        from .models import Referral
        referral = Referral.objects.filter(referred_user=user, status='pending').select_related('inviter').first()
        if not referral:
            return False

        # Check qualifying criteria
        has_sent_messages = user.sent_messages.filter(is_deleted=False).exists() if hasattr(user, 'sent_messages') else False
        has_joined_rooms = user.room_memberships.exists() if hasattr(user, 'room_memberships') else False
        has_profile_content = bool(
            hasattr(user, 'profile') and (
                user.profile.avatar or user.profile.avatar_preset or user.profile.bio or user.profile.interests.exists()
            )
        )

        if has_sent_messages or has_joined_rooms or has_profile_content:
            referral.status = 'qualified'
            referral.qualified_at = timezone.now()
            referral.save(update_fields=['status', 'qualified_at'])

            # Trigger badge evaluation for the inviter
            BadgeService.evaluate_user_badge(referral.inviter)
            return True

        return False

    @staticmethod
    def get_inviter_progress(user):
        """Returns referral stats and progress to the next badge tier for a user."""
        if not user or not user.is_authenticated:
            return {
                'joined_count': 0,
                'qualified_count': 0,
                'next_tier': 'connector',
                'needed_for_next': 3,
                'progress_pct': 0,
            }

        from .models import Referral
        all_referrals = Referral.objects.filter(inviter=user)
        joined_count = all_referrals.count()
        qualified_count = all_referrals.filter(status='qualified').count()

        if qualified_count < 3:
            next_tier = 'connector'
            needed_for_next = 3 - qualified_count
            progress_pct = int((qualified_count / 3) * 100)
        elif qualified_count < 5:
            next_tier = 'trusted_member'
            needed_for_next = 5 - qualified_count
            progress_pct = int((qualified_count / 5) * 100)
        else:
            next_tier = None
            needed_for_next = 0
            progress_pct = 100

        return {
            'joined_count': joined_count,
            'qualified_count': qualified_count,
            'next_tier': next_tier,
            'needed_for_next': needed_for_next,
            'progress_pct': progress_pct,
        }


class BadgeService:
    @staticmethod
    def evaluate_user_badge(user):
        """
        Evaluates and updates user's profile badge based on activity, qualified referrals, and ratings.
        Hierarchy: Trusted Member > Connector > Active Member > New Member.
        """
        if not user or not user.is_authenticated or not hasattr(user, 'profile'):
            return 'new_member'

        profile = user.profile
        from .models import Referral
        qualified_referrals = Referral.objects.filter(inviter=user, status='qualified').count()
        messages_sent = user.sent_messages.filter(is_deleted=False).count() if hasattr(user, 'sent_messages') else 0
        has_interests = profile.interests.exists()
        has_bio = bool(profile.bio)
        has_avatar = bool(profile.avatar or profile.avatar_preset)

        # Ratings check
        ratings = user.received_ratings.all() if hasattr(user, 'received_ratings') else []
        rating_count = ratings.count() if hasattr(ratings, 'count') else len(ratings)
        avg_score = 0.0
        if rating_count >= 3:
            from django.db.models import Avg
            avg_score = ratings.aggregate(Avg('score'))['score__avg'] or 0.0

        is_trusted = (
            (messages_sent >= 10 and rating_count >= 3 and avg_score >= 4.0 and qualified_referrals >= 1)
            or (qualified_referrals >= 5 and messages_sent >= 5)
        )

        if is_trusted:
            new_badge = 'trusted_member'
        elif qualified_referrals >= 3:
            new_badge = 'connector'
        elif messages_sent >= 3 or (has_interests and has_avatar and has_bio):
            new_badge = 'active_member'
        else:
            new_badge = 'new_member'

        if profile.badge != new_badge:
            profile.badge = new_badge
            profile.save(update_fields=['badge'])

        return new_badge

    @staticmethod
    def get_badge_details(badge_key):
        from .models import COMMUNITY_BADGES
        return COMMUNITY_BADGES.get(badge_key, COMMUNITY_BADGES['new_member'])

