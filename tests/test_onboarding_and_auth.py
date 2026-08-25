"""
Automated unit and integration tests for the decoupled Registration & Profile Onboarding flow.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from unittest.mock import patch
from apps.accounts.models import Profile, Interest, PRESET_AVATARS, generate_unique_user_identity
from apps.accounts.services import VerificationService

User = get_user_model()

class OnboardingAndAuthTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Seed test interests
        self.gaming = Interest.objects.create(name='Gaming', slug='gaming', emoji='🎮')
        self.music = Interest.objects.create(name='Music', slug='music', emoji='🎵')
        self.tech = Interest.objects.create(name='Technology', slug='tech', emoji='💻')
        self.travel = Interest.objects.create(name='Travel', slug='travel', emoji='✈️')
        self.food = Interest.objects.create(name='Food', slug='food', emoji='🍳')
        self.art = Interest.objects.create(name='Art', slug='art', emoji='🎨')

    def test_unique_user_identity_generator(self):
        """Validates that generate_unique_user_identity creates valid, unique identities."""
        uname, dname, preset = generate_unique_user_identity()
        self.assertTrue(uname.startswith('user_'))
        self.assertTrue(dname.startswith('User '))
        self.assertIn(preset, PRESET_AVATARS)

    @patch('apps.accounts.services.BrevoEmailProvider.send_otp')
    def test_step1_registration_with_email_and_real_otp(self, mock_send_otp):
        """Step 1: User signs up with Email + Real OTP + Password."""
        mock_send_otp.return_value = (True, "Sent")
        email = "rohan.sharma@example.com"
        
        # 1. Dispatch real OTP challenge
        success, msg, cooldown = VerificationService.send_otp_challenge(email, purpose='signup')
        self.assertTrue(success)

        # Retrieve generated OTP hash record
        from apps.accounts.models import OTPVerification
        otp_rec = OTPVerification.objects.filter(identifier=email, is_used=False).first()
        self.assertIsNotNone(otp_rec)

        # Re-generate or simulate verification with matching OTP
        # We test verify_otp_challenge with invalid OTP
        is_valid, _ = VerificationService.verify_otp_challenge(email, "000000", purpose='signup')
        self.assertFalse(is_valid)

        # Let's test form submission directly with valid OTP
        # Create OTP challenge and verify
        from apps.accounts.services import generate_otp, hash_otp
        raw_otp = "852963"
        otp_rec.otp_hash = hash_otp(raw_otp)
        otp_rec.save()

        form_data = {
            'name': 'Rohan Sharma',
            'email': email,
            'otp': raw_otp,
            'password': 'SecurePassword123!',
            'confirm_password': 'SecurePassword123!',
        }

        resp = self.client.post(reverse('accounts:register'), data=form_data)
        # Should redirect to Step 2 Onboarding
        self.assertRedirects(resp, reverse('accounts:onboarding'))

        # Check that user and profile exist with specified name
        user = User.objects.filter(email=email).first()
        self.assertIsNotNone(user)
        self.assertTrue(user.is_verified)
        self.assertTrue(user.username.startswith('user_'))
        self.assertFalse(user.profile.is_temporary_name)
        self.assertEqual(user.profile.display_name, 'Rohan Sharma')
        self.assertIn(user.profile.avatar_preset, PRESET_AVATARS)

    def test_signup_validation_for_name_and_email(self):
        """Validates that Sign Up strictly requires Name and valid Email."""
        # Missing Name
        resp1 = self.client.post(reverse('accounts:register'), data={
            'name': '',
            'email': 'user@example.com',
            'otp': '123456',
            'password': 'SecurePassword123!',
            'confirm_password': 'SecurePassword123!',
        })
        self.assertEqual(resp1.status_code, 200)
        self.assertIn('name', resp1.context['form'].errors)

        # Invalid Email
        resp2 = self.client.post(reverse('accounts:register'), data={
            'name': 'Valid Name',
            'email': 'invalid-email-format',
            'otp': '123456',
            'password': 'SecurePassword123!',
            'confirm_password': 'SecurePassword123!',
        })
        self.assertEqual(resp2.status_code, 200)
        self.assertIn('email', resp2.context['form'].errors)

    def test_step2_onboarding_save_profile(self):
        """Step 2: User customizes Gender, Avatar, and Interests (Reuses Name from signup)."""
        # Create registered user
        user = User.objects.create_user(
            username='user_5555',
            email='maya@example.com',
            password='TestPassword123!',
            is_verified=True
        )
        user.profile.display_name = 'Maya Patel'
        user.profile.is_temporary_name = False
        user.profile.save()

        self.client.force_login(user)

        # GET onboarding page
        get_resp = self.client.get(reverse('accounts:onboarding'))
        self.assertEqual(get_resp.status_code, 200)

        # POST profile details (Gender, Interests, Avatar)
        post_data = {
            'avatar_preset': 'panda',
            'gender': 'female',
            'interests': [self.gaming.id, self.music.id, self.tech.id]
        }
        post_resp = self.client.post(reverse('accounts:onboarding'), data=post_data)
        self.assertRedirects(post_resp, reverse('core:home'))

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.display_name, 'Maya Patel')
        self.assertFalse(user.profile.is_temporary_name)
        self.assertEqual(user.profile.gender, 'female')
        self.assertEqual(user.profile.avatar_preset, 'panda')
        self.assertEqual(user.profile.interests.count(), 3)
        self.assertTrue(user.profile.is_profile_completed)

    def test_step2_onboarding_skip_for_now(self):
        """Step 2: User skips profile setup and lands directly on Home with functional profile."""
        user = User.objects.create_user(
            username='user_9999',
            email='skipper@example.com',
            password='TestPassword123!',
            is_verified=True
        )
        user.profile.display_name = 'Alex Skipper'
        user.profile.is_temporary_name = False
        user.profile.save()

        self.client.force_login(user)

        skip_resp = self.client.get(reverse('accounts:onboarding') + '?skip=1')
        self.assertRedirects(skip_resp, reverse('core:home'))

        # Profile remains functional
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.display_name, 'Alex Skipper')
        self.assertFalse(user.profile.is_temporary_name)

    def test_min_and_max_interests_limit_enforcement(self):
        """Selecting fewer than 3 or more than 5 interests raises validation errors."""
        user = User.objects.create_user(
            username='user_1234',
            email='gamer@example.com',
            password='TestPassword123!',
            is_verified=True
        )
        self.client.force_login(user)

        # 1. Fewer than 3 interests
        post_data_under = {
            'gender': 'male',
            'avatar_preset': 'fox',
            'interests': [self.gaming.id, self.music.id]
        }
        resp1 = self.client.post(reverse('accounts:onboarding'), data=post_data_under)
        self.assertEqual(resp1.status_code, 200)
        self.assertIn('interests', resp1.context['form'].errors)

        # 2. More than 5 interests
        anime = Interest.objects.create(name='Anime', slug='anime', emoji='🎞️')
        post_data_over = {
            'gender': 'male',
            'avatar_preset': 'fox',
            'interests': [self.gaming.id, self.music.id, self.tech.id, self.travel.id, self.food.id, anime.id]
        }
        resp2 = self.client.post(reverse('accounts:onboarding'), data=post_data_over)
        self.assertEqual(resp2.status_code, 200)
        self.assertIn('interests', resp2.context['form'].errors)

    def test_login_with_email_and_phone(self):
        """User can log in using their email or phone number."""
        user = User.objects.create_user(
            username='user_7777',
            email='login.test@example.com',
            phone_number='9876500000',
            password='MySecurePassword123!',
            is_verified=True
        )

        # 1. Login with Email
        email_resp = self.client.post(reverse('accounts:login'), {
            'username': 'login.test@example.com',
            'password': 'MySecurePassword123!',
        })
        self.assertRedirects(email_resp, reverse('core:home'))

        self.client.logout()

        # 2. Login with Phone Number
        phone_resp = self.client.post(reverse('accounts:login'), {
            'username': '9876500000',
            'password': 'MySecurePassword123!',
        })
        self.assertRedirects(phone_resp, reverse('core:home'))
