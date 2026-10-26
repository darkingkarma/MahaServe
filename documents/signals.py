from django.conf import settings
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from .models import ResidentProfile, DocumentRequest, Notification


User = get_user_model()


# Automatically create a profile for a newly registered resident.
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_resident_profile(sender, instance, created, **kwargs):
    if created and not instance.is_staff:
        ResidentProfile.objects.get_or_create(user=instance)


# Remember the previous request status before it is changed.
@receiver(pre_save, sender=DocumentRequest)
def remember_previous_request_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_status = None
        return

    instance._previous_status = (
        DocumentRequest.objects
        .filter(pk=instance.pk)
        .values_list("status", flat=True)
        .first()
    )


# Notify the resident when staff changes the request status.
@receiver(post_save, sender=DocumentRequest)
def notify_resident_of_status_change(sender, instance, created, **kwargs):
    if created:
        return

    previous_status = getattr(instance, "_previous_status", None)

    if previous_status is None or previous_status == instance.status:
        return

    status_messages = {
        "pending": (
            "Request Pending",
            "Your document request is pending review."
        ),
        "under_review": (
            "Request Under Review",
            "Your document request is now being reviewed by barangay staff."
        ),
        "approved": (
            "Request Approved",
            "Your document request has been approved."
        ),
        "rejected": (
            "Request Rejected",
            "Your document request has been rejected."
        ),
        "released": (
            "Document Released",
            "Your document is ready. Please visit Barangay Mahayahay Hall "
            "to claim it."
        ),
    }

    notification_data = status_messages.get(instance.status)

    if not notification_data:
        return

    title, message = notification_data

    Notification.objects.create(
        recipient=instance.resident,
        title=title,
        message=(
            f"{message} Document: {instance.document_type.name}."
        ),
        link=f"/resident/requests/",
        is_read=False,
    )


# Notify staff when a resident submits a new document request.
@receiver(post_save, sender=DocumentRequest)
def notify_staff_of_new_request(sender, instance, created, **kwargs):
    if not created:
        return
        
    staff_members = User.objects.filter(is_staff=True)

    notifications = [
        Notification(
            recipient=staff_member,
            title="New Document Request",
            message=(
                f"{instance.resident.username} submitted a request for "
                f"{instance.document_type.name}."
            ),
            link=f"/staff/requests/{instance.pk}/",
            is_read=False,
        )
        for staff_member in staff_members
    ]

    if notifications:
        Notification.objects.bulk_create(notifications)
