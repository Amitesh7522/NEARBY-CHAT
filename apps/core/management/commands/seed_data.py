"""
Management command to seed realistic test data for Nearby Chat.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.accounts.models import Profile, UserPreference, Interest
from apps.rooms.models import Room, RoomMember, RoomMessage
from apps.chat.models import Conversation, ConversationParticipant, Message, MessageStatus
from apps.chat.services import ChatService
from apps.safety.models import Block, Report

User = get_user_model()

class Command(BaseCommand):
    help = 'Seeds initial test users, rooms, and conversations for Nearby Chat.'

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding Nearby Chat development data...")

        # 1. Create Predefined Interest Catalog
        interests_data = [
            {'slug': 'tech-ai', 'name': 'Tech & AI', 'emoji': '💻', 'category': 'Technology'},
            {'slug': 'gaming', 'name': 'Gaming', 'emoji': '🎮', 'category': 'Entertainment'},
            {'slug': 'music', 'name': 'Music & Beats', 'emoji': '🎵', 'category': 'Creative'},
            {'slug': 'fitness', 'name': 'Fitness & Gym', 'emoji': '🏋️', 'category': 'Lifestyle'},
            {'slug': 'movies-anime', 'name': 'Movies & Anime', 'emoji': '🎬', 'category': 'Entertainment'},
            {'slug': 'travel-food', 'name': 'Travel & Food', 'emoji': '✈️', 'category': 'Lifestyle'},
            {'slug': 'books', 'name': 'Books & Ideas', 'emoji': '📚', 'category': 'Education'},
            {'slug': 'startups', 'name': 'Startups & Business', 'emoji': '🚀', 'category': 'Career'},
            {'slug': 'art-design', 'name': 'Art & Design', 'emoji': '🎨', 'category': 'Creative'},
            {'slug': 'chill-chat', 'name': 'Chill & Chat', 'emoji': '☕', 'category': 'Social'},
        ]
        
        interest_objs = {}
        for item in interests_data:
            obj, _ = Interest.objects.get_or_create(
                slug=item['slug'],
                defaults={'name': item['name'], 'emoji': item['emoji'], 'category': item['category']}
            )
            interest_objs[item['slug']] = obj

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(interest_objs)} standard interests."))

        # 2. Create Superuser / Admin
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@nearbychat.app',
                'is_staff': True,
                'is_superuser': True,
                'is_verified': True,
            }
        )
        if created:
            admin_user.set_password('admin12345')
            admin_user.save()
            admin_user.profile.display_name = 'Admin Officer'
            admin_user.profile.bio = 'Platform Administrator & Moderator'
            admin_user.profile.avatar_preset = 'robot'
            admin_user.profile.save()
            admin_user.profile.interests.add(interest_objs['tech-ai'], interest_objs['startups'])
            self.stdout.write(self.style.SUCCESS("Created admin user (admin / admin12345)"))

        # 3. Create Realistic Users with Interests
        test_users_data = [
            {
                'username': 'priya_sharma',
                'display_name': 'Priya Sharma',
                'email': 'priya@example.com',
                'bio': 'Coffee enthusiast, UX designer & amateur photographer ☕📸',
                'gender': 'female',
                'location': 'Mumbai, Maharashtra',
                'avatar_preset': 'fox',
                'interests': ['tech-ai', 'art-design', 'chill-chat'],
                'is_online': True,
                'lang': 'en',
            },
            {
                'username': 'rahul_verma',
                'display_name': 'Rahul Verma',
                'email': 'rahul@example.com',
                'bio': 'Full-stack developer | Open source lover | Football fanatic ⚽',
                'gender': 'male',
                'location': 'Bengaluru, Karnataka',
                'avatar_preset': 'panda',
                'interests': ['tech-ai', 'gaming', 'fitness'],
                'is_online': True,
                'lang': 'en',
            },
            {
                'username': 'ananya_sen',
                'display_name': 'Ananya Sen',
                'email': 'ananya@example.com',
                'bio': 'Bookworm 📚 | Exploring the city on weekends | Always up for good conversations',
                'gender': 'female',
                'location': 'New Delhi, Delhi',
                'avatar_preset': 'cat',
                'interests': ['books', 'travel-food', 'chill-chat'],
                'is_online': True,
                'lang': 'hi',
            },
            {
                'username': 'aarav_patel',
                'display_name': 'Aarav Patel',
                'email': 'aarav@example.com',
                'bio': 'Startup founder & tech geek 🚀 Building the next big thing.',
                'gender': 'male',
                'location': 'Pune, Maharashtra',
                'avatar_preset': 'astro',
                'interests': ['startups', 'tech-ai', 'gaming'],
                'is_online': False,
                'lang': 'en',
            },
            {
                'username': 'rohan_gupta',
                'display_name': 'Rohan Gupta',
                'email': 'rohan@example.com',
                'bio': 'Music producer 🎵 Electronic beats & acoustic vibes.',
                'gender': 'male',
                'location': 'Hyderabad, Telangana',
                'avatar_preset': 'lion',
                'interests': ['music', 'movies-anime', 'gaming'],
                'is_online': True,
                'lang': 'hi',
            },
        ]

        created_users = []
        for u_data in test_users_data:
            user, u_created = User.objects.get_or_create(
                username=u_data['username'],
                defaults={
                    'email': u_data['email'],
                    'is_verified': True,
                }
            )
            if u_created:
                user.set_password('password123')
                user.save()
            
            profile = user.profile
            profile.display_name = u_data['display_name']
            profile.bio = u_data['bio']
            profile.gender = u_data['gender']
            profile.location_name = u_data['location']
            profile.avatar_preset = u_data['avatar_preset']
            profile.is_online = u_data['is_online']
            profile.show_online_status = True
            profile.allow_random_chat = True
            profile.save()

            # Assign interests
            for slug in u_data.get('interests', []):
                if slug in interest_objs:
                    profile.interests.add(interest_objs[slug])
            profile.show_online_status = True
            profile.allow_random_chat = True
            profile.save()

            pref = user.preferences
            pref.language = u_data['lang']
            pref.save()

            created_users.append(user)
            self.stdout.write(f"Created user: {user.username} (password: password123)")

        # 3. Create Public Rooms
        rooms_data = [
            {
                'name': 'Tech & Startups India',
                'topic': 'Technology',
                'description': 'Discussions on coding, startups, AI, and building products in India.',
                'creator': created_users[1], # Rahul
            },
            {
                'name': 'Coffee & Conversations',
                'topic': 'Casual',
                'description': 'Chill and talk about life, weekend plans, hobbies, and random thoughts.',
                'creator': created_users[0], # Priya
            },
            {
                'name': 'Music & Indie Beats',
                'topic': 'Music',
                'description': 'Share playlists, discover indie artists, and discuss favourite tracks.',
                'creator': created_users[4], # Rohan
            },
            {
                'name': 'Delhi / NCR Hangout',
                'topic': 'City',
                'description': 'Connect with folks living in or visiting Delhi, Noida, and Gurgaon.',
                'creator': created_users[2], # Ananya
            },
        ]

        for r_data in rooms_data:
            room, r_created = Room.objects.get_or_create(
                name=r_data['name'],
                defaults={
                    'topic': r_data['topic'],
                    'description': r_data['description'],
                    'creator': r_data['creator'],
                    'is_public': True,
                }
            )
            if r_created:
                # Add creator as owner
                RoomMember.objects.get_or_create(room=room, user=r_data['creator'], defaults={'role': 'owner'})
                # Add other users as members
                for u in created_users:
                    RoomMember.objects.get_or_create(room=room, user=u, defaults={'role': 'member'})
                
                # Add sample messages
                RoomMessage.objects.create(
                    room=room,
                    sender=r_data['creator'],
                    content=f"Welcome everyone to {room.name}! Feel free to introduce yourself."
                )

        # 4. Create Sample Direct Conversation between Priya and Rahul
        user1 = created_users[0] # Priya
        user2 = created_users[1] # Rahul
        
        conv, c_created = ChatService.get_or_create_direct_conversation(user1, user2)

        if c_created:
            m1 = Message.objects.create(
                conversation=conv,
                sender=user1,
                content="Hey Rahul! Have you checked out the new tech meetup in Indiranagar?"
            )
            MessageStatus.objects.create(message=m1, user=user2, status='read')

            m2 = Message.objects.create(
                conversation=conv,
                sender=user2,
                content="Hey Priya! Yes, I was actually planning to attend this Saturday. Are you going?"
            )
            MessageStatus.objects.create(message=m2, user=user1, status='sent')

        self.stdout.write(self.style.SUCCESS("Successfully seeded Nearby Chat database!"))
