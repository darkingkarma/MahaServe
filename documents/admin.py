
from django.contrib import admin
from .models import DocumentType, DocumentRequest


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "fee", "is_available")
    list_filter = ("is_available",)
    search_fields = ("name",)


@admin.register(DocumentRequest)
class DocumentRequestAdmin(admin.ModelAdmin):
    list_display = (
        "resident",
        "document_type",
        "status",
        "submitted_at",
    )
    list_filter = ("status", "submitted_at")
    search_fields = ("resident__username", "document_type__name")
