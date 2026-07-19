"""Etiqueta {% static_v %}: como {% static %} pero, solo en desarrollo, agrega
?v=<mtime> para bustear la cache del navegador cuando el archivo cambia.

Motivacion: en produccion los estaticos los sirve WhiteNoise con nombres
hasheados (ManifestStaticFilesStorage), asi que cada cambio ya invalida la
cache solo. Pero en dev (runserver) los estaticos se sirven sin Cache-Control,
y el navegador reusa por heuristica versiones viejas de JS/CSS: al editar, por
ejemplo, un .js, la pagina sigue ejecutando el codigo cacheado hasta un
Ctrl+F5. Agregar ?v=<mtime> cambia la URL en cada edicion y fuerza el refresco.

En produccion (DEBUG=False) la etiqueta devuelve exactamente lo mismo que
{% static %} (URL hasheada), sin tocar nada.
"""
import os

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_v(path):
    url = static(path)
    if settings.DEBUG:
        ruta_absoluta = finders.find(path)
        if ruta_absoluta and os.path.exists(ruta_absoluta):
            mtime = int(os.path.getmtime(ruta_absoluta))
            separador = "&" if "?" in url else "?"
            url = f"{url}{separador}v={mtime}"
    return url
