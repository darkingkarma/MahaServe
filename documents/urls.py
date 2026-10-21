from django.urls import path
from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("staff/dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("register/", views.register, name="register"),
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
]
