from django.urls import path
from . import views

app_name = "core_pages"

urlpatterns = [
    path("", views.home, name="home"),
]
