from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db import IntegrityError

from .models import DocumentType, DocumentRequest
import resend
from django.conf import settings

# ==========================================
# LANDING PAGE
# ==========================================
def landing(request):
    return render(request, "documents/landing.html")


# ==========================================
# CITIZEN REGISTRATION
# ==========================================

def register(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect("admin_dashboard")
        return redirect("resident_dashboard")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if not username or not email or not password or not confirm_password:
            messages.error(request, "Please fill in all fields.")

        elif password != confirm_password:
            messages.error(request, "Passwords do not match.")

        elif len(password) < 8:
            messages.error(request, "Password must be at least 8 characters.")

        elif User.objects.filter(username__iexact=username).exists():
            messages.error(request, "Username is already taken.")

        elif User.objects.filter(email__iexact=email).exists():
            messages.error(request, "Email is already registered.")

        else:
            try:
                User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                )

                messages.success(
                    request,
                    "Registration successful! You can now log in."
                )

                return redirect("login")

            except IntegrityError:
                messages.error(
                    request,
                    "Unable to create the account. Please try again."
                )

    return render(request, "documents/register.html")


# ==========================================
# SHARED LOGIN FOR CITIZENS AND STAFF
# ==========================================

def login(request):
    # Redirect users who are already logged in.
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect("admin_dashboard")

        return redirect("resident_dashboard")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is not None:
            auth_login(request, user)

            # Staff and superusers go to the staff dashboard.
            if user.is_staff:
                return redirect("admin_dashboard")

            # Ordinary citizens go to their resident dashboard.
            return redirect("resident_dashboard")

        messages.error(request, "Invalid username or password.")

    return render(request, "documents/login.html")


# ==========================================
# LOGOUT
# ==========================================

@login_required(login_url="/login/")
def logout(request):
    if request.method == "POST":
        auth_logout(request)
        return redirect("landing")

    # Require POST for logout.
    return redirect("landing")


# ==========================================
# CITIZEN / RESIDENT DASHBOARD
# ==========================================


@login_required(login_url="/login/")
def resident_dashboard(request):
    my_requests = DocumentRequest.objects.filter(
        resident=request.user
    ).select_related("document_type").order_by("-submitted_at")

    document_types = DocumentType.objects.filter(
        is_available=True
    ).order_by("name")

    context = {
        "my_requests": my_requests,
        "document_types": document_types,
        "total_requests": my_requests.count(),
        "pending_requests": my_requests.filter(
            status="pending"
        ).count(),
        "released_requests": my_requests.filter(
            status="released"
        ).count(),
    }

    return render(
        request,
        "documents/resident_dashboard.html",
        context
    )


@login_required(login_url="/login/")
def request_document(request, document_id):
    document = get_object_or_404(
        DocumentType,
        id=document_id,
        is_available=True
    )

    if request.method == "POST":
        purpose = request.POST.get("purpose", "").strip()

        if not purpose:
            messages.error(request, "Please enter the purpose of your request.")
        else:
            DocumentRequest.objects.create(
                resident=request.user,
                document_type=document,
                purpose=purpose
            )

            messages.success(
                request,
                "Your document request has been submitted successfully!"
            )
            return redirect("resident_dashboard")

    return render(
        request,
        "documents/request_document.html",
        {"document": document}
    )


# ==========================================
# STAFF / ADMIN DASHBOARD
# ==========================================

@staff_member_required(login_url="/login/")
def admin_dashboard(request):
    context = {
        "total_requests": DocumentRequest.objects.count(),

        "pending_requests": DocumentRequest.objects.filter(
            status="pending"
        ).count(),

        "approved_requests": DocumentRequest.objects.filter(
            status="approved"
        ).count(),

        "released_requests": DocumentRequest.objects.filter(
            status="released"
        ).count(),

        # Count registered citizen accounts, not document requests.
        "total_residents": User.objects.filter(
            is_staff=False,
            is_superuser=False,
        ).count(),

        "total_document_types": DocumentType.objects.count(),

        "recent_requests": DocumentRequest.objects.select_related(
            "resident",
            "document_type",
        ).order_by("-submitted_at")[:5],
    }

    return render(
        request,
        "documents/admin_dashboard.html",
        context,
    )

@staff_member_required(login_url="/login/")
def request_details(request, request_id):
    document_request = get_object_or_404(
        DocumentRequest.objects.select_related(
            "resident",
            "document_type"
        ),
        id=request_id
    )

    context = {
        "document_request": document_request,
    }

    return render(
        request,
        "documents/request_details.html",
        context
    )

@staff_member_required(login_url="/login/")
def manage_requests(request):
    requests_list = DocumentRequest.objects.select_related(
        "resident",
        "document_type",
    ).order_by("-submitted_at")

    context = {
        "requests_list": requests_list,
        "status_choices": DocumentRequest.STATUS_CHOICES,
    }

    return render(
        request,
        "documents/manage_requests.html",
        context,
    )



@staff_member_required(login_url="/login/")
def update_request(request, request_id):
    if request.method != "POST":
        return redirect("manage_requests")

    document_request = get_object_or_404(
        DocumentRequest.objects.select_related(
            "resident",
            "document_type",
        ),
        id=request_id,
    )

    new_status = request.POST.get("status", "").strip()
    remarks = request.POST.get("remarks", "").strip()

    valid_statuses = dict(DocumentRequest.STATUS_CHOICES)

    if new_status not in valid_statuses:
        messages.error(request, "Invalid request status.")
        return redirect("request_details", request_id=request_id)

    old_status = document_request.status

    document_request.status = new_status
    document_request.remarks = remarks
    document_request.save(
        update_fields=["status", "remarks", "updated_at"]
    )

    messages.success(request, "Request updated successfully.")

    # Send an email only when the status actually changes.
    if old_status != new_status:
        recipient_email = document_request.resident.email

        if settings.RESEND_API_KEY and recipient_email:
            try:
                resend.api_key = settings.RESEND_API_KEY

                resend.Emails.send({
                    "from": "onboarding@resend.dev",
                    "to": [recipient_email],
                    "subject": (
                        f"MahaServe: Your {document_request.document_type.name} "
                        "request has been updated"
                    ),
                    "text": (
                        f"Hello {document_request.resident.username},\n\n"
                        f"Your request for "
                        f"{document_request.document_type.name} has been updated.\n\n"
                        f"New status: {valid_statuses[new_status]}\n"
                        f"Staff remarks: {remarks or 'No additional remarks.'}\n\n"
                        "Please log in to MahaServe to track your request.\n\n"
                        "Thank you,\nMahaServe"
                    ),
                })

            except Exception as e:
                print("RESEND EMAIL ERROR:", repr(e))

                messages.warning(
                    request,
                    "The request was updated, but the email notification "
                    "could not be sent. Check the terminal for details.",
                )

    return redirect("manage_requests")


# ==========================================
# DOCUMENT MANAGEMENT - STAFF CRUD
# ==========================================

@staff_member_required(login_url="/login/")
def manage_documents(request):
    document_types = DocumentType.objects.all().order_by("name")

    return render(
        request,
        "documents/manage_documents.html",
        {
            "document_types": document_types,
        },
    )



@staff_member_required(login_url="/login/")
def add_document(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        fee = request.POST.get("fee", "").strip()
        image = request.FILES.get("image")
        is_available = request.POST.get("is_available") == "on"

        if not name or not fee:
            messages.error(request, "Name and fee are required.")

        elif DocumentType.objects.filter(name__iexact=name).exists():
            messages.error(request, "This document type already exists.")

        elif image and not image.content_type.startswith("image/"):
            messages.error(request, "Please upload a valid image file.")

        else:
            try:
                from decimal import Decimal, InvalidOperation

                parsed_fee = Decimal(fee)

                if not parsed_fee.is_finite() or parsed_fee < 0:
                    raise InvalidOperation

                DocumentType.objects.create(
                    name=name,
                    description=description,
                    fee=parsed_fee,
                    image=image,
                    is_available=is_available,
                )

                messages.success(
                    request,
                    "Document type added successfully!"
                )
                return redirect("manage_documents")

            except (InvalidOperation, ValueError):
                messages.error(
                    request,
                    "Please enter a valid, non-negative fee."
                )

    return render(request, "documents/add_document.html")





@staff_member_required(login_url="/login/")
def edit_document(request, document_id):
    document = get_object_or_404(DocumentType, id=document_id)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        fee = request.POST.get("fee", "").strip()
        image = request.FILES.get("image")
        is_available = request.POST.get("is_available") == "on"

        if not name or not fee:
            messages.error(request, "Name and fee are required.")

        elif DocumentType.objects.filter(
            name__iexact=name
        ).exclude(id=document_id).exists():
            messages.error(request, "This document type already exists.")

        elif image and not image.content_type.startswith("image/"):
            messages.error(request, "Please upload a valid image file.")

        else:
            try:
                from decimal import Decimal, InvalidOperation

                parsed_fee = Decimal(fee)

                if not parsed_fee.is_finite() or parsed_fee < 0:
                    raise InvalidOperation

                # Keep a reference to the old image.
                old_image = document.image if image else None

                # Update document details.
                document.name = name
                document.description = description
                document.fee = parsed_fee
                document.is_available = is_available

                if image:
                    document.image = image

                # Save the new image and document details first.
                document.save()

                # Delete the old image after the replacement is saved.
                if old_image:
                    try:
                        old_image.delete(save=False)
                    except Exception:
                        # The document was saved, but old-image cleanup failed.
                        messages.warning(
                            request,
                            "Document updated, but the old image may still remain in Cloudinary."
                        )
                        return redirect("manage_documents")

                messages.success(
                    request,
                    "Document type updated successfully!"
                )
                return redirect("manage_documents")

            except (InvalidOperation, ValueError):
                messages.error(
                    request,
                    "Please enter a valid, non-negative fee."
                )

    return render(
        request,
        "documents/edit_document.html",
        {"document": document}
    )


@staff_member_required(login_url="/login/")
def delete_document(request, document_id):
    if request.method != "POST":
        return redirect("manage_documents")

    document = get_object_or_404(DocumentType, id=document_id)

    try:
        # Delete the database record first.
        # If existing requests protect it, deletion will fail.
        document.delete()

        # Delete the Cloudinary image after the record is deleted.
        if document.image:
            document.image.delete(save=False)

        messages.success(
            request,
            "Document type and its image deleted successfully!"
        )

    except IntegrityError:
        messages.error(
            request,
            "This document type cannot be deleted because it has existing document requests. Deactivate it instead."
        )

    return redirect("manage_documents")


@staff_member_required(login_url="/login/")
def toggle_document_availability(request, document_id):
    if request.method != "POST":
        return redirect("manage_documents")

    document = get_object_or_404(DocumentType, id=document_id)
    document.is_available = not document.is_available
    document.save(update_fields=["is_available"])

    messages.success(
        request,
        f"{document.name} availability updated successfully.",
    )

    return redirect("manage_documents")
