from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("staff/dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("register/", views.register, name="register"),
    path("login/",auth_views.LoginView.as_view(template_name="documents/login.html"),name="login",),
    path("logout/",auth_views.LogoutView.as_view(next_page="landing"),name="logout",),
]