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
    # Prevent staff accounts from using the resident dashboard.
    if request.user.is_staff:
        return redirect("admin_dashboard")

    my_requests = DocumentRequest.objects.filter(
        resident=request.user
    ).select_related(
        "document_type"
    ).order_by("-submitted_at")

    context = {
        "my_requests": my_requests,

        "total_requests": my_requests.count(),

        "pending_requests": my_requests.filter(
            status="pending"
        ).count(),

        "released_requests": my_requests.filter(
            status="released"
        ).count(),

        "document_types": DocumentType.objects.filter(
            is_available=True
        ),
    }

    return render(
        request,
        "documents/resident_dashboard.html",
        context,
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

        if not name or not fee:
            messages.error(request, "Name and fee are required.")

        elif DocumentType.objects.filter(name__iexact=name).exists():
            messages.error(request, "This document type already exists.")

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
                    is_available=True,
                )

                messages.success(request, "Document type added successfully!")
                return redirect("manage_documents")

            except (InvalidOperation, ValueError):
                messages.error(request, "Please enter a valid, non-negative fee.")

    return render(request, "documents/add_document.html")


@staff_member_required(login_url="/login/")
def edit_document(request, document_id):
    document = get_object_or_404(DocumentType, id=document_id)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        fee = request.POST.get("fee", "").strip()

        if not name or not fee:
            messages.error(request, "Name and fee are required.")

        elif DocumentType.objects.filter(
            name__iexact=name
        ).exclude(id=document.id).exists():
            messages.error(request, "Another document type has this name.")

        else:
            try:
                from decimal import Decimal, InvalidOperation

                parsed_fee = Decimal(fee)

                if not parsed_fee.is_finite() or parsed_fee < 0:
                    raise InvalidOperation

                document.name = name
                document.description = description
                document.fee = parsed_fee
                document.save()

                messages.success(request, "Document type updated successfully!")
                return redirect("manage_documents")

            except (InvalidOperation, ValueError):
                messages.error(request, "Please enter a valid, non-negative fee.")

    return render(
        request,
        "documents/edit_document.html",
        {"document": document},
    )


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
