"""
Punto de entrada del servidor de produccion.
Levanta la aplicacion Django con Waitress escuchando en toda la red local.
Se usa un archivo propio en vez de waitress-serve para que las rutas del
.env y del proyecto sean absolutas y no dependan del directorio desde el
que Windows ejecute la tarea programada.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from waitress import serve

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ruben_curto_apicultura.settings")

from ruben_curto_apicultura.wsgi import application

if __name__ == "__main__":
    serve(application, host="0.0.0.0", port=8000, threads=8)
