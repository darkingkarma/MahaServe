
import os

import resend
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a test email through Resend"

    def handle(self, *args, **options):
        api_key = settings.RESEND_API_KEY

        if not api_key:
            raise CommandError(
                "RESEND_API_KEY is missing. Check your .env file and settings.py."
            )

        recipient = input("Enter your recipient email address: ").strip()

        if not recipient or "@" not in recipient:
            raise CommandError("Please enter a valid email address.")

        resend.api_key = api_key

        try:
            result = resend.Emails.send({
                "from": "onboarding@resend.dev",
                "to": [recipient],
                "subject": "MahaServe Email Test",
                "text": (
                    "Hello! This is a test email from MahaServe. "
                    "Your Resend email integration is being tested successfully."
                ),
            })

            self.stdout.write(
                self.style.SUCCESS(f"Resend response: {result}")
            )

        except Exception as exc:
            raise CommandError(
                f"Resend email failed: {exc}"
            ) from exc
