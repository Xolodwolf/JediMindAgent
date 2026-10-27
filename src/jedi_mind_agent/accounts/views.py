from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import redirect, render
from django.urls import reverse_lazy


def register(request):
    if request.user.is_authenticated:
        return redirect("index")
    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.save())
        messages.success(request, "Аккаунт создан. Начнём с короткого теста.")
        return redirect("index")
    return render(request, "registration/register.html", {"form": form})


class PasswordChangeView(auth_views.PasswordChangeView):
    """Back to the agent with a message instead of a separate "password changed" page."""

    # A unique name: django.contrib.admin ships its own registration/password_change_form.html.
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("index")

    def form_valid(self, form):
        messages.success(self.request, "Пароль изменён.")
        return super().form_valid(form)
