
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ResidentProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_resident_profile(sender, instance, created, **kwargs):
    if created and not instance.is_staff:
        ResidentProfile.objects.get_or_create(user=instance)
