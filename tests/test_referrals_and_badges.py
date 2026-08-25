"""
Automated tests for Invite Friends, Referral Tracking, and Profile Badge System.
Validates invite code generation, anti-abuse checks, qualification triggers, badge hierarchy, and share endpoints.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from apps.accounts.models import Profile, Referral, Interest, COMMUNITY_BADGES
from apps.accounts.services import ReferralService, BadgeService
from apps.chat.services import ChatService
from apps.chat.models import ConversationRating

User = get_user_model()

class ReferralAndBadgeTests(TestCase):
    def setUp(self):
        self.user_inviter = User.objects.create_user(
            username='aarav',
            email='aarav@example.com',
            password='TestPassword123!',
            phone_number='9876543201',
            is_verified=True
        )
        self.user_invitee = User.objects.create_user(
            username='priya',
            email='priya@example.com',
            password='TestPassword123!',
            phone_number='9876543202',
            is_verified=True
        )
        Profile.objects.get_or_create(user=self.user_inviter, defaults={'display_name': 'Aarav'})
        Profile.objects.get_or_create(user=self.user_invitee, defaults={'display_name': 'Priya'})

        self.client = Client()

    def test_invite_code_generated(self):
        """Every user profile gets a unique 8-character invite code."""
        code = self.user_inviter.profile.invite_code
        self.assertTrue(len(code) == 8)
        self.assertTrue(code.isalnum())

    def test_referral_creation_and_self_referral_prevention(self):
        """Prevents self-referrals and creates legitimate referrals."""
        # 1. Self referral attempt
        self_ref = ReferralService.record_referral(
            invite_code=self.user_inviter.profile.invite_code,
            referred_user=self.user_inviter
        )
        self.assertIsNone(self_ref)

        # 2. Legitimate referral
        ref = ReferralService.record_referral(
            invite_code=self.user_inviter.profile.invite_code,
            referred_user=self.user_invitee
        )
        self.assertIsNotNone(ref)
        self.assertEqual(ref.inviter, self.user_inviter)
        self.assertEqual(ref.referred_user, self.user_invitee)
        self.assertEqual(ref.status, 'pending')

        # 3. Duplicate referral on same user -> blocked
        dup_ref = ReferralService.record_referral(
            invite_code=self.user_inviter.profile.invite_code,
            referred_user=self.user_invitee
        )
        self.assertIsNone(dup_ref)

    def test_referral_qualification_via_chat_activity(self):
        """Referral qualifies when the new user performs activity (sends a message)."""
        ref = ReferralService.record_referral(
            invite_code=self.user_inviter.profile.invite_code,
            referred_user=self.user_invitee
        )
        self.assertEqual(ref.status, 'pending')

        # Invitee sends a message in a conversation
        conv, _ = ChatService.get_or_create_direct_conversation(self.user_invitee, self.user_inviter)
        ChatService.send_message(conv.id, self.user_invitee, "Hello Aarav, I joined!")

        # Refresh referral
        ref.refresh_from_db()
        self.assertEqual(ref.status, 'qualified')
        self.assertIsNotNone(ref.qualified_at)

    def test_badge_progression_hierarchy(self):
        """Tests badge advancement from New Member -> Active Member -> Connector -> Trusted Member."""
        # 1. Default badge is new_member
        badge = BadgeService.evaluate_user_badge(self.user_inviter)
        self.assertEqual(badge, 'new_member')

        # 2. Active member: user completes profile or sends >= 3 messages
        conv, _ = ChatService.get_or_create_direct_conversation(self.user_inviter, self.user_invitee)
        for i in range(3):
            ChatService.send_message(conv.id, self.user_inviter, f"Message {i}")
        badge = BadgeService.evaluate_user_badge(self.user_inviter)
        self.assertEqual(badge, 'active_member')

        # 3. Connector: user gets 3 qualified referrals
        for i in range(3):
            friend = User.objects.create_user(
                username=f'friend_{i}',
                email=f'friend_{i}@example.com',
                password='TestPassword123!',
                phone_number=f'987654329{i}',
                is_verified=True
            )
            r = Referral.objects.create(
                inviter=self.user_inviter,
                referred_user=friend,
                invite_code=self.user_inviter.profile.invite_code,
                status='qualified'
            )

        badge = BadgeService.evaluate_user_badge(self.user_inviter)
        self.assertEqual(badge, 'connector')

        # 4. Trusted member: >= 10 messages, >= 3 ratings with avg >= 4.0, >= 1 qualified referral
        for i in range(8):
            ChatService.send_message(conv.id, self.user_inviter, f"Extra message {i}")

        # Add 3 high ratings for inviter
        for i in range(3):
            rater = User.objects.create_user(username=f'rater_{i}', email=f'rater_{i}@example.com', password='TestPassword123!')
            c, _ = ChatService.get_or_create_direct_conversation(rater, self.user_inviter)
            ConversationRating.objects.create(
                conversation=c,
                rater=rater,
                ratee=self.user_inviter,
                score=5,
                tags=['Friendly', 'Respectful']
            )

        badge = BadgeService.evaluate_user_badge(self.user_inviter)
        self.assertEqual(badge, 'trusted_member')

    def test_invite_landing_and_registration_attribution(self):
        """Invite link sets session code and attributes new account on signup."""
        inviter_code = self.user_inviter.profile.invite_code

        # Open landing link
        resp = self.client.get(f'/invite/{inviter_code}/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/accounts/register/?ref={inviter_code}', resp.url)
        self.assertEqual(self.client.session.get('invite_code'), inviter_code)

        # Register new user with OTP challenge
        email = 'new_friend@example.com'
        from apps.accounts.models import OTPVerification
        from apps.accounts.services import hash_otp
        from django.utils import timezone
        from datetime import timedelta
        raw_otp = '999111'
        OTPVerification.objects.create(
            identifier=email,
            otp_hash=hash_otp(raw_otp),
            purpose='signup',
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        reg_resp = self.client.post('/accounts/register/', {
            'name': 'New Friend',
            'email': email,
            'otp': raw_otp,
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!',
        })
        self.assertEqual(reg_resp.status_code, 302)

        # Check Referral record created
        new_user = User.objects.get(email=email)
        referral = Referral.objects.filter(referred_user=new_user).first()
        self.assertIsNotNone(referral)
        self.assertEqual(referral.inviter, self.user_inviter)

    def test_invite_friends_view_renders_correctly(self):
        """The /invite/ page displays the invite link and community progress."""
        self.client.force_login(self.user_inviter)
        resp = self.client.get('/invite/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Invite Friends')
        self.assertContains(resp, self.user_inviter.profile.invite_code)
        self.assertContains(resp, 'Your Community Progress')
