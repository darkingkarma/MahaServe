from django.shortcuts import render, redirect, get_object_or_404
from groq import Groq
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db import IntegrityError
from decimal import Decimal
from .models import DocumentType, DocumentRequest, ResidentProfile, DocumentPayment
import resend
from django.conf import settings
from django.urls import reverse
import requests
from django.views.decorators.http import require_POST

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

        # Resident profile fields
        contact_number = request.POST.get("contact_number", "").strip()
        house_number = request.POST.get("house_number", "").strip()
        street = request.POST.get("street", "").strip()
        purok = request.POST.get("purok", "").strip()
        date_of_birth = request.POST.get("date_of_birth", "").strip()
        sex = request.POST.get("sex", "").strip()

        if not username or not email or not password or not confirm_password:
            messages.error(request, "Please fill in all required fields.")

        elif password != confirm_password:
            messages.error(request, "Passwords do not match.")

        elif len(password) < 8:
            messages.error(request, "Password must be at least 8 characters.")

        elif User.objects.filter(username__iexact=username).exists():
            messages.error(request, "Username is already taken.")

        elif User.objects.filter(email__iexact=email).exists():
            messages.error(request, "Email is already registered.")

        elif sex and sex not in ["male", "female", "prefer_not_to_say"]:
            messages.error(request, "Please select a valid sex option.")

        else:
            try:
                from datetime import date
                from django.db import transaction
                from .models import ResidentProfile

                parsed_date = None
                if date_of_birth:
                    try:
                        parsed_date = date.fromisoformat(date_of_birth)
                        if parsed_date > date.today():
                            messages.error(
                                request,
                                "Date of birth cannot be in the future."
                            )
                            return render(request, "documents/register.html")
                    except ValueError:
                        messages.error(
                            request,
                            "Please enter a valid date of birth."
                        )
                        return render(request, "documents/register.html")

                with transaction.atomic():
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=password,
                    )

                    ResidentProfile.objects.create(
                        user=user,
                        contact_number=contact_number,
                        house_number=house_number,
                        street=street,
                        purok=purok,
                        date_of_birth=parsed_date,
                        sex=sex,
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
# PAYMONGO PAYMENTS
# ==========================================

@login_required(login_url="/login/")
def create_payment(request, request_id):
    document_request = get_object_or_404(
        DocumentRequest.objects.select_related("document_type"),
        id=request_id,
        resident=request.user,
        status="approved",
    )

    amount = document_request.document_type.fee

    if amount <= Decimal("0.00"):
        messages.error(
            request,
            "This document does not require payment."
        )
        return redirect("my_requests")

    if not settings.PAYMONGO_SECRET_KEY:
        messages.error(
            request,
            "Payment service is not configured."
        )
        return redirect("my_requests")

    # Reuse an existing pending checkout if available.
    existing_payment = DocumentPayment.objects.filter(
        document_request=document_request,
        status="pending",
    ).exclude(
        checkout_url=""
    ).first()

    if existing_payment:
        return redirect(existing_payment.checkout_url)

    payment = DocumentPayment.objects.create(
        document_request=document_request,
        amount=amount,
        status="pending",
    )

    amount_in_centavos = int(amount * 100)

    checkout_data = {
        "data": {
            "attributes": {
                "line_items": [
                    {
                        "currency": "PHP",
                        "amount": amount_in_centavos,
                        "name": document_request.document_type.name,
                        "quantity": 1,
                    }
                ],
                "payment_method_types": [
                    "gcash"
                ],
                "success_url": request.build_absolute_uri(
                    f"/payment/success/?request_id={document_request.id}"
                ),
                "cancel_url": request.build_absolute_uri(
                    f"/payment/cancel/?request_id={document_request.id}"
                ),
                "description": (
                    f"MahaServe - "
                    f"{document_request.document_type.name}"
                ),
                "reference_number": f"MAHASERVE-{payment.id}",
            }
        }
    }

    try:
        response = requests.post(
            "https://api.paymongo.com/v1/checkout_sessions",
            auth=(settings.PAYMONGO_SECRET_KEY, ""),
            json=checkout_data,
            timeout=30,
        )

        response_data = response.json()

        if response.status_code not in (200, 201):
            payment.status = "failed"
            payment.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

            print("PayMongo error:", response_data)

            messages.error(
                request,
                "Could not create checkout. Please try again."
            )

            return redirect("my_requests")

        checkout_session = response_data["data"]
        attributes = checkout_session["attributes"]

        payment.checkout_session_id = checkout_session["id"]
        payment.checkout_url = attributes["checkout_url"]

        payment.payment_intent_id = attributes.get(
            "payment_intent",
            {}
        ).get(
            "id",
            ""
        )

        payment.save(
            update_fields=[
                "checkout_session_id",
                "checkout_url",
                "payment_intent_id",
                "updated_at",
            ]
        )

        return redirect(payment.checkout_url)

    except (
        requests.RequestException,
        ValueError,
        KeyError,
    ) as error:

        payment.status = "failed"

        payment.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        print("PayMongo checkout error:", error)

        messages.error(
            request,
            "Payment service is temporarily unavailable."
        )

        return redirect("my_requests")


@login_required(login_url="/login/")
def payment_success(request):
    request_id = request.GET.get("request_id")

    document_request = get_object_or_404(
        DocumentRequest,
        id=request_id,
        resident=request.user,
    )

    payment = DocumentPayment.objects.filter(
        document_request=document_request,
        status="pending",
    ).exclude(
        checkout_session_id=""
    ).order_by(
        "-created_at"
    ).first()

    if not payment:
        already_paid = DocumentPayment.objects.filter(
            document_request=document_request,
            status="paid",
        ).exists()

        if already_paid:
            messages.success(
                request,
                "Your payment has already been verified."
            )
        else:
            messages.warning(
                request,
                "No pending payment was found. Please check My Requests."
            )

        return redirect("my_requests")

    try:
        response = requests.get(
            (
                "https://api.paymongo.com/v1/checkout_sessions/"
                f"{payment.checkout_session_id}"
            ),
            auth=(settings.PAYMONGO_SECRET_KEY, ""),
            timeout=30,
        )

        if response.status_code != 200:
            messages.warning(
                request,
                "We could not verify your payment yet. "
                "Please check again later."
            )

            return redirect("my_requests")

        session_data = response.json()["data"]
        attributes = session_data["attributes"]

        # Make sure the PayMongo session is the one
        # stored for this MahaServe payment.
        if session_data["id"] != payment.checkout_session_id:
            messages.error(
                request,
                "Payment verification failed."
            )

            return redirect("my_requests")

        expected_amount = int(payment.amount * 100)

        confirmed = any(
            item.get("attributes", {}).get("status") == "paid"
            and item.get("attributes", {}).get("amount") == expected_amount
            and item.get("attributes", {}).get(
                "currency",
                ""
            ).upper() == "PHP"
            for item in attributes.get("payments", [])
        )

        if confirmed:
            payment.status = "paid"

            payment.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

            messages.success(
                request,
                "Payment verified successfully!"
            )

        else:
            messages.warning(
                request,
                "PayMongo has not confirmed your payment yet. "
                "Your payment status has not been changed."
            )

    except (
        requests.RequestException,
        ValueError,
        KeyError,
    ) as error:

        print("PayMongo verification error:", error)

        messages.warning(
            request,
            "We could not verify your payment right now. "
            "Please try again later."
        )

    return redirect("my_requests")


@login_required(login_url="/login/")
def payment_cancel(request):
    messages.info(
        request,
        "Checkout was cancelled. "
        "Your document request remains unchanged."
    )

    return redirect("my_requests")

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

        # Create a status-specific message.
        if new_status == "pending":
            status_message = (
                "Your document request has been submitted and is "
                "waiting for review by the barangay staff."
            )

        elif new_status == "under_review":
            status_message = (
                "The barangay staff is currently reviewing your "
                "document request. Please wait for further updates."
            )

        elif new_status == "approved":
            status_message = (
                "Good news! Your document request has been approved. "
                "Please log in to MahaServe to check the next steps."
            )

        elif new_status == "rejected":
            status_message = (
                "Unfortunately, your document request has been rejected. "
                "Please review the staff remarks below or contact "
                "Barangay Mahayahay for clarification."
            )

        elif new_status == "released":
            status_message = (
                "Your document is ready for collection! Please visit "
                "Barangay Mahayahay Hall to claim your document. "
                "Bring a valid ID and your request details. "
                "Please coordinate with the barangay staff regarding "
                "collection hours."
            )

        else:
            status_message = (
                "Your document request status has been updated. "
                "Please log in to MahaServe to view the latest information."
            )

        if settings.RESEND_API_KEY and recipient_email:
            try:
                resend.api_key = settings.RESEND_API_KEY

                email_text = (
                    f"Hello {document_request.resident.username},\n\n"
                    f"Your request for "
                    f"{document_request.document_type.name} has been updated.\n\n"
                    f"Request status: {valid_statuses[new_status]}\n\n"
                    f"{status_message}\n\n"
                    f"Staff remarks: "
                    f"{remarks or 'No additional remarks.'}\n\n"
                    "You can log in to MahaServe to track your request.\n\n"
                    "Thank you,\n"
                    "MahaServe\n"
                    "Barangay Mahayahay Document Request System"
                )

                resend.Emails.send({
                    "from": "onboarding@resend.dev",
                    "to": [recipient_email],
                    "subject": (
                        f"MahaServe: Your "
                        f"{document_request.document_type.name} "
                        f"request is {valid_statuses[new_status]}"
                    ),
                    "text": email_text,
                })

            except Exception as e:
                print("RESEND EMAIL ERROR:", repr(e))

                messages.warning(
                    request,
                    "The request was updated, but the email notification "
                    "could not be sent. Check the terminal for details.",
                )

        elif not recipient_email:
            messages.warning(
                request,
                "The request was updated, but the resident has no email "
                "address registered.",
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


@login_required(login_url="/login/")
def resident_profile(request):
    if request.user.is_staff:
        return redirect("admin_dashboard")

    profile, created = ResidentProfile.objects.get_or_create(
        user=request.user
    )

    if request.method == "POST":
        contact_number = request.POST.get("contact_number", "").strip()
        house_number = request.POST.get("house_number", "").strip()
        street = request.POST.get("street", "").strip()
        purok = request.POST.get("purok", "").strip()
        date_of_birth = request.POST.get("date_of_birth", "").strip()
        sex = request.POST.get("sex", "").strip()

        if sex and sex not in ["male", "female", "prefer_not_to_say"]:
            messages.error(request, "Please select a valid sex option.")
        else:
            from datetime import date

            parsed_date = None
            if date_of_birth:
                try:
                    parsed_date = date.fromisoformat(date_of_birth)
                    if parsed_date > date.today():
                        messages.error(
                            request,
                            "Date of birth cannot be in the future."
                        )
                        return render(
                            request,
                            "documents/resident_profile.html",
                            {"profile": profile},
                        )
                except ValueError:
                    messages.error(
                        request,
                        "Please enter a valid date of birth."
                    )
                    return render(
                        request,
                        "documents/resident_profile.html",
                        {"profile": profile},
                    )

            profile.contact_number = contact_number
            profile.house_number = house_number
            profile.street = street
            profile.purok = purok
            profile.date_of_birth = parsed_date
            profile.sex = sex
            profile.save()

            messages.success(request, "Your profile has been updated!")
            return redirect("resident_profile")

    return render(
        request,
        "documents/resident_profile.html",
        {"profile": profile},
    )

@login_required(login_url="/login/")
def my_requests(request):
    if request.user.is_staff:
        return redirect("admin_dashboard")

    requests = DocumentRequest.objects.filter(
        resident=request.user
    ).select_related(
        "document_type"
    ).order_by("-submitted_at")

    return render(
        request,
        "documents/my_requests.html",
        {
            "requests": requests,
        }
    )


@login_required(login_url="/login/")
def ai_assistant(request):
    answer = ""
    question = ""

    if request.method == "POST":
        question = request.POST.get("question", "").strip()

        if not question:
            messages.error(request, "Please enter your question.")

        else:
            try:
                client = Groq(api_key=settings.GROQ_API_KEY)

                response = client.chat.completions.create(
                    model="openai/gpt-oss-20b",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are MahaServe Assistant, a helpful AI "
                                "assistant for the Barangay Mahayahay "
                                "Document Request System in the Philippines. "
                                "Answer questions about registering, logging "
                                "in, requesting barangay documents, fees, "
                                "payments, request statuses, and collecting "
                                "released documents. Keep answers simple, "
                                "polite, and concise. Explain that fees depend "
                                "on the document type shown in MahaServe. "
                                "Residents should check My Requests for their "
                                "actual request status. When a document is "
                                "released, instruct the resident to visit "
                                "Barangay Mahayahay Hall and bring a valid ID. "
                                "Never invent official fees, requirements, "
                                "processing times, or barangay policies. "
                                "If you do not know an official detail, advise "
                                "the resident to contact barangay staff. "
                                "Do not claim to access the user's account, "
                                "database, or live request status."
                            ),
                        },
                        {
                            "role": "user",
                            "content": question,
                        },
                    ],
                )

                answer = response.choices[0].message.content or (
                    "Sorry, I couldn't generate an answer. Please try again."
                )

            except Exception:
                messages.error(
                    request,
                    "The AI assistant is temporarily unavailable. "
                    "Please try again later.",
                )

    return render(
        request,
        "documents/ai_assistant.html",
        {
            "answer": answer,
            "question": question,
        },
    )
