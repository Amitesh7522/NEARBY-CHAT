"""
Automated tests for PWA, Push Notifications, and Location-Based Proximity Filters.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
import json

from apps.accounts.models import Profile
from apps.notifications.models import WebPushSubscription
from apps.core.views import calculate_distance_km

User = get_user_model()

class PWAAndProximityTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(
            username='arjun',
            email='arjun@example.com',
            password='TestPassword123!',
            phone_number='9876543201',
            is_verified=True
        )
        self.user2 = User.objects.create_user(
            username='priya',
            email='priya@example.com',
            password='TestPassword123!',
            phone_number='9876543202',
            is_verified=True
        )
        self.profile1 = self.user1.profile
        self.profile1.display_name = 'Arjun'
        self.profile1.latitude = 19.0760
        self.profile1.longitude = 72.8777
        self.profile1.location_name = 'Mumbai'
        self.profile1.allow_random_chat = True
        self.profile1.save()

        self.profile2 = self.user2.profile
        self.profile2.display_name = 'Priya'
        self.profile2.latitude = 19.0800
        self.profile2.longitude = 72.8800
        self.profile2.location_name = 'Mumbai'
        self.profile2.allow_random_chat = True
        self.profile2.save()

    def test_haversine_distance_calculation(self):
        """Validates great-circle distance calculation between coordinates."""
        # Distance between coordinates (~0.5 - 0.6 km apart in Mumbai)
        dist = calculate_distance_km(19.0760, 72.8777, 19.0800, 72.8800)
        self.assertIsNotNone(dist)
        self.assertGreater(dist, 0.3)
        self.assertLess(dist, 1.0)

        # Distance when coordinates are None
        self.assertIsNone(calculate_distance_km(None, None, 19.0800, 72.8800))
        self.assertIsNone(calculate_distance_km(19.0760, 72.8777, None, None))

    def test_push_subscribe_api(self):
        """Registers a web push subscription endpoint for an authenticated user."""
        self.client.force_login(self.user1)
        url = reverse('notifications:push_subscribe')
        
        payload = {
            'endpoint': 'https://fcm.googleapis.com/fcm/send/test-token-12345',
            'p256dh': 'test-p256dh-key',
            'auth': 'test-auth-secret'
        }
        res = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get('success'))

        # Verify persisted in database
        sub = WebPushSubscription.objects.filter(user=self.user1).first()
        self.assertIsNotNone(sub)
        self.assertEqual(sub.endpoint, payload['endpoint'])

    def test_update_location_api_with_fuzzing(self):
        """Updates user coordinates and applies privacy fuzzing offset."""
        self.client.force_login(self.user1)
        url = reverse('accounts:api_update_location')

        original_lat = 28.6139 # New Delhi
        original_lon = 77.2090

        payload = {
            'latitude': original_lat,
            'longitude': original_lon,
            'location_name': 'New Delhi'
        }
        res = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get('success'))

        self.profile1.refresh_from_db()
        self.assertEqual(self.profile1.location_name, 'New Delhi')
        # Ensure coordinate is close but has a slight privacy fuzzing offset
        self.assertAlmostEqual(float(self.profile1.latitude), original_lat, delta=0.01)
        self.assertAlmostEqual(float(self.profile1.longitude), original_lon, delta=0.01)

    def test_home_view_distance_annotation_and_radius_filter(self):
        """Home discovery view annotates distances and filters by radius."""
        self.client.force_login(self.user1)
        
        # 1. Any distance
        res = self.client.get(reverse('core:home'))
        self.assertEqual(res.status_code, 200)
        self.assertIn('discover_users', res.context)

        # 2. Radius filter < 5 km (Priya is ~0.5 km away, so should be included)
        res_radius = self.client.get(reverse('core:home') + '?radius=5')
        self.assertEqual(res_radius.status_code, 200)
        self.assertIn(self.user2, [u for u in res_radius.context['discover_users']])

        # 3. Same city filter
        res_city = self.client.get(reverse('core:home') + '?radius=city')
        self.assertEqual(res_city.status_code, 200)
        self.assertIn(self.user2, [u for u in res_city.context['discover_users']])
