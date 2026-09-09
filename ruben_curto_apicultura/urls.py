from django.contrib import admin
from django.templatetags.static import static
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('favicon.ico', RedirectView.as_view(
        url=static('icons/isotipo_ruben_curto_apicultura.svg'), permanent=True,
    )),
    path('admin/', admin.site.urls),
    path('', include("main.urls"))
]
