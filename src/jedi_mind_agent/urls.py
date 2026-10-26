from django.contrib import admin
from django.urls import include, path

from jedi_mind_agent.web import views as web_views

admin.site.site_header = "JediMindAgent — администрирование"
admin.site.site_title = "JediMindAgent"
admin.site.index_title = "Настройки агента и данные"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("jedi_mind_agent.accounts.urls")),
    path("api/v1/", include("jedi_mind_agent.product.urls")),
    path("health", web_views.health, name="health"),
    path("health/db", web_views.database_health, name="health-db"),
    path("", web_views.index, name="index"),
]
