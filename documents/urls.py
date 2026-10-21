
from django.urls import path
from . import views

urlpatterns = [
    # Landing page
    path("", views.landing, name="landing"),

    # Authentication
    path("register/", views.register, name="register"),
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),

    # Dashboards
    path("resident/dashboard/",views.resident_dashboard,name="resident_dashboard",),
    path("staff/dashboard/",views.admin_dashboard,name="admin_dashboard",),

    # Document Management - Staff CRUD
    path("staff/documents/",views.manage_documents,name="manage_documents",),
    path("staff/documents/add/",views.add_document,name="add_document",),
    path("staff/documents/<int:document_id>/edit/",views.edit_document,name="edit_document",),
    path("staff/documents/<int:document_id>/toggle-availability/",views.toggle_document_availability,name="toggle_document_availability",),
]
