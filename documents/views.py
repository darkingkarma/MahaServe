from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import IntegrityError
from django.contrib.admin.views.decorators import staff_member_required
from .models import DocumentType, DocumentRequest



def landing(request):
    return render(request, "documents/landing.html")

def register(request):
    if request.user.is_authenticated:
        return redirect("landing")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if not username or not email or not password:
            messages.error(request, "Please fill in all required fields.")

        elif password != confirm_password:
            messages.error(request, "Passwords do not match.")

        elif User.objects.filter(username__iexact=username).exists():
            messages.error(request, "That username is already taken.")

        elif User.objects.filter(email__iexact=email).exists():
            messages.error(request, "That email is already registered.")

        else:
            try:
                User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                )
                messages.success(
                    request,
                    "Account created successfully! You can now log in."
                )
                return redirect("login")
            except IntegrityError:
                messages.error(
                    request,
                    "Unable to create your account. Please try again."
                )

    return render(request, "documents/register.html")


def login(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect("admin_dashboard")
        return redirect("landing")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            auth_login(request, user)

            if user.is_staff:
                return redirect("admin_dashboard")

            return redirect("landing")

        messages.error(request, "Invalid username or password.")

    return render(request, "documents/login.html")


def logout(request):
    if request.method == "POST":
        auth_logout(request)

    return redirect("landing")

@staff_member_required(login_url="/admin/login/")
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
        "total_residents": DocumentRequest.objects.values(
            "resident"
        ).distinct().count(),
        "total_document_types": DocumentType.objects.count(),
        "recent_requests": DocumentRequest.objects.select_related(
            "resident", "document_type"
        ).order_by("-submitted_at")[:5],
    }

    return render(
        request,
        "documents/admin_dashboard.html",
        context,
    )
