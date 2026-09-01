from django.core.management.base import BaseCommand
from apps.private_rooms.services import PrivateRoomService


class Command(BaseCommand):
    help = "Cleans up expired private rooms and purges temporary uploaded files from storage."

    def add_arguments(self, parser):
        parser.add_argument(
            '--files-only',
            action='store_true',
            help='Only delete uploaded media files from disk, keeping room metadata.',
        )

    def handle(self, *args, **options):
        files_only = options.get('files_only', False)
        rooms_count, files_count = PrivateRoomService.cleanup_expired_rooms(purge_files_only=files_only)
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully cleaned up {rooms_count} expired private rooms and purged {files_count} media files."
            )
        )
