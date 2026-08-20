from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, Profile, UserPreference

@receiver(post_save, sender=User)
def create_or_save_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(
            user=instance,
            defaults={'display_name': instance.username}
        )
        UserPreference.objects.get_or_create(user=instance)
    else:
        if hasattr(instance, 'profile'):
            instance.profile.save()
        if hasattr(instance, 'preferences'):
            instance.preferences.save()
