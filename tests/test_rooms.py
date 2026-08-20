from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.rooms.models import Room, RoomMember, RoomMessage
from apps.rooms.services import RoomService

User = get_user_model()

class RoomsTestCase(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(username='host', email='host@example.com', password='Password123!')
        self.member = User.objects.create_user(username='guest', email='guest@example.com', password='Password123!')

    def test_room_creation(self):
        """Creates room and automatically designates creator as owner."""
        room = RoomService.create_room(
            creator=self.creator,
            name="Gaming Room",
            topic="Gaming",
            description="Discuss games"
        )
        self.assertEqual(room.name, "Gaming Room")
        self.assertTrue(RoomMember.objects.filter(room=room, user=self.creator, role='owner').exists())

    def test_join_and_leave_room(self):
        """Users can join and leave rooms."""
        room = RoomService.create_room(creator=self.creator, name="Tech Talks")
        
        member, created = RoomService.join_room(self.member, room)
        self.assertTrue(created)
        self.assertEqual(room.member_count, 2)

        RoomService.leave_room(self.member, room)
        self.assertEqual(room.member_count, 1)

    def test_room_messaging(self):
        """Joined members can send messages to room."""
        room = RoomService.create_room(creator=self.creator, name="Music Club")
        RoomService.join_room(self.member, room)

        msg = RoomService.send_room_message(
            room_id=room.id,
            sender=self.member,
            content="Hello club members!",
            client_msg_id="rm_test_1"
        )
        self.assertEqual(msg['content'], "Hello club members!")
        self.assertEqual(RoomMessage.objects.filter(room=room).count(), 1)
