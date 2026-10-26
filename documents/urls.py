from django.urls import path
from . import views

urlpatterns = [
    # Landing page
    path("", views.landing, name="landing"),

    # Authentication
    path("register/", views.register, name="register"),
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),

    # Resident dashboards and profile
    path(
        "resident/dashboard/",
        views.resident_dashboard,
        name="resident_dashboard",
    ),

    path(
        "resident/search-documents/",
        views.search_documents,
        name="search_documents",
    ),
    path(
        "resident/profile/",
        views.resident_profile,
        name="resident_profile",
    ),
    path(
        "resident/requests/",
        views.my_requests,
        name="my_requests",
    ),

        # MahaServe AI Assistant
    path(
        "resident/assistant/",
        views.ai_assistant,
        name="ai_assistant",
    ),

    # Resident document requests
    path(
        "resident/request/<int:document_id>/",
        views.request_document,
        name="request_document",
    ),

    # PayMongo payment checkout
    path(
        "resident/pay/<int:request_id>/",
        views.create_payment,
        name="create_payment",
    ),

    path("payment/success/", views.payment_success, name="payment_success"),
    path("payment/cancel/", views.payment_cancel, name="payment_cancel"),

    # Staff dashboard
    path(
        "staff/dashboard/",
        views.admin_dashboard,
        name="admin_dashboard",
    ),

    # Staff document management
    path(
        "staff/documents/",
        views.manage_documents,
        name="manage_documents",
    ),
    path(
        "staff/documents/add/",
        views.add_document,
        name="add_document",
    ),
    path(
        "staff/documents/<int:document_id>/edit/",
        views.edit_document,
        name="edit_document",
    ),
    path(
        "staff/documents/delete/<int:document_id>/",
        views.delete_document,
        name="delete_document",
    ),
    path(
        "staff/documents/<int:document_id>/toggle-availability/",
        views.toggle_document_availability,
        name="toggle_document_availability",
    ),

    # Staff request management
    path(
        "staff/requests/",
        views.manage_requests,
        name="manage_requests",
    ),
    path(
        "staff/requests/<int:request_id>/",
        views.request_details,
        name="request_details",
    ),
    path(
        "staff/requests/<int:request_id>/update/",
        views.update_request,
        name="update_request",
    ),

    path(
        "notifications/",
        views.notification_list,
        name="notification_list",
    ),
    path(
        "notifications/<int:notification_id>/read/",
        views.mark_notification_read,
        name="mark_notification_read",
    ),
]