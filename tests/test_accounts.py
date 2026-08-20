import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.accounts.models import Profile, UserPreference, OTPVerification, Interest
from apps.accounts.services import VerificationService, hash_otp

User = get_user_model()

class AccountsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='Password123!'
        )
        self.interest_gaming = Interest.objects.create(name='Gaming', slug='gaming', emoji='🎮')

    def test_user_creation_creates_profile_and_preference(self):
        """Signals must auto-create Profile and UserPreference upon user registration."""
        self.assertTrue(hasattr(self.user, 'profile'))
        self.assertTrue(hasattr(self.user, 'preferences'))
        self.assertEqual(self.user.profile.get_display_name(), 'testuser')
        self.assertEqual(self.user.preferences.language, 'en')

    def test_user_login_with_username_and_email(self):
        """User can log in using either username or email."""
        # 1. Login with username
        logged_in = self.client.login(username='testuser', password='Password123!')
        self.assertTrue(logged_in)
        self.client.logout()

        # 2. Login via email via HTTP view
        res = self.client.post(reverse('accounts:login'), {
            'username': 'test@example.com',
            'password': 'Password123!'
        })
        self.assertEqual(res.status_code, 302)

    def test_registration_flow(self):
        """New user signup properly creates user, sets display name and interests."""
        res = self.client.post(reverse('accounts:register'), {
            'username': 'newuser',
            'display_name': 'New Person',
            'email': 'new@example.com',
            'interests': [self.interest_gaming.id],
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!'
        })
        self.assertEqual(res.status_code, 302)
        new_u = User.objects.filter(username='newuser').first()
        self.assertIsNotNone(new_u)
        self.assertEqual(new_u.profile.display_name, 'New Person')
        self.assertTrue(new_u.profile.interests.filter(slug='gaming').exists())

    def test_otp_verification_service(self):
        """Tests OTP dispatch and verification service."""
        success, msg = VerificationService.send_otp_challenge('9876543210', purpose='signup')
        self.assertTrue(success)

        record = OTPVerification.objects.filter(identifier='9876543210', is_used=False).first()
        self.assertIsNotNone(record)

        # Invalidate with wrong OTP
        self.assertFalse(VerificationService.verify_otp_challenge('9876543210', '000000', purpose='signup'))

    def test_profile_update(self):
        """User can update bio, location, visibility, and cartoon avatar preset."""
        self.client.login(username='testuser', password='Password123!')
        res = self.client.post(reverse('accounts:edit_profile'), {
            'display_name': 'Updated Name',
            'avatar_preset': 'fox',
            'bio': 'Updated Bio test',
            'gender': 'male',
            'location_name': 'Mumbai',
            'show_online_status': True,
            'allow_random_chat': True,
        })
        self.assertEqual(res.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.display_name, 'Updated Name')
        self.assertEqual(self.user.profile.location_name, 'Mumbai')
        self.assertEqual(self.user.profile.avatar_preset, 'fox')
        self.assertIn('fox.svg', self.user.profile.get_avatar_url())

    def test_account_deletion(self):
        """Account deletion cleanly cascades and removes user records."""
        self.client.login(username='testuser', password='Password123!')
        res = self.client.post(reverse('accounts:delete_account'), {
            'password': 'Password123!'
        })
        self.assertEqual(res.status_code, 302)
        self.assertFalse(User.objects.filter(username='testuser').exists())
