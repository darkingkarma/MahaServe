
from django.db import models
from django.contrib.auth.models import User


class DocumentType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    image = models.ImageField(
        upload_to="document_types/",
        blank=True,
        null=True,
    )
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class DocumentRequest(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("under_review", "Under Review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("released", "Released"),
    ]

    resident = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="document_requests",
    )
    document_type = models.ForeignKey(
        DocumentType,
        on_delete=models.PROTECT,
        related_name="requests",
    )
    purpose = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    remarks = models.TextField(blank=True)

    def __str__(self):
        return f"{self.resident.username} - {self.document_type.name}"

class DocumentPayment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("failed", "Failed"),
    ]

    document_request = models.ForeignKey(
        DocumentRequest,
        on_delete=models.CASCADE,
        related_name="payments",
    )

    amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
    )

    status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default="pending",
    )

    checkout_session_id = models.CharField(
        max_length=150,
        blank=True,
    )

    checkout_url = models.URLField(
        max_length=500,
        blank=True,
    )

    payment_intent_id = models.CharField(
        max_length=150,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return (
            f"Payment for request #{self.document_request_id} "
            f"- {self.status}"
        )

class ResidentProfile(models.Model):
    SEX_CHOICES = [
        ("male", "Male"),
        ("female", "Female"),
        ("prefer_not_to_say", "Prefer not to say"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="resident_profile",
    )
    contact_number = models.CharField(max_length=20, blank=True)
    house_number = models.CharField(max_length=100, blank=True)
    street = models.CharField(max_length=150, blank=True)
    purok = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    sex = models.CharField(
        max_length=20,
        choices=SEX_CHOICES,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of {self.user.username}"


class Notification(models.Model):
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=150)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    link = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.recipient.username}"
