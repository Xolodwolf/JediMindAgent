from django.contrib.auth import views as auth_views
from django.urls import path

from jedi_mind_agent.accounts import views

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", views.register, name="register"),
    path("password/", views.PasswordChangeView.as_view(), name="password_change"),
]
