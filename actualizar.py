"""
Actualizador y vigilante del servidor.
Lo ejecuta la tarea programada "Actualizar Apicultura" cada 10 minutos y
al encender la PC. En cada corrida:
  1. Consulta el repositorio remoto. Si hay commits nuevos en la rama de
     produccion detiene el servidor, aplica los cambios (codigo,
     dependencias, migraciones y archivos estaticos) y lo vuelve a levantar.
  2. Verifica que el servidor este escuchando en el puerto. Si no lo esta
     (arranque de la PC o caida), lo levanta.
Esta escrito en Python y no en .bat porque Python carga el archivo completo
en memoria antes de ejecutarlo: asi el propio actualizador puede ser
reemplazado por git pull sin romperse a mitad de camino.
"""

import subprocess
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PYTHON = BASE_DIR / "venv" / "Scripts" / "python.exe"
LOG = BASE_DIR / "actualizador.log"

RAMA = "main"
PUERTO = 8000
TAREA_SERVIDOR = "Servidor Apicultura"


def log(mensaje):
    marca = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG.open("a", encoding="utf-8") as archivo:
        archivo.write(f"[{marca}] {mensaje}\n")


def ejecutar(comando, obligatorio=True):
    resultado = subprocess.run(
        comando,
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if resultado.returncode != 0 and obligatorio:
        raise RuntimeError(
            f"Fallo {' '.join(str(parte) for parte in comando)}\n{resultado.stderr.strip()}"
        )
    return resultado.stdout


def pid_del_servidor():
    # Devuelve el PID del proceso que escucha en el puerto, o None si no hay ninguno
    salida = ejecutar(["netstat", "-ano", "-p", "tcp"], obligatorio=False)
    for linea in salida.splitlines():
        partes = linea.split()
        if len(partes) >= 5 and partes[3] == "LISTENING" and partes[1].endswith(f":{PUERTO}"):
            return int(partes[4])
    return None


def esperar(condicion, segundos):
    for _ in range(segundos * 2):
        if condicion():
            return True
        time.sleep(0.5)
    return False


def detener_servidor():
    """
    Primero baja la tarea programada, que mata el arbol completo de
    procesos. Si el servidor se habia lanzado a mano y el puerto sigue
    ocupado, mata directamente al proceso que lo tiene.
    """
    ejecutar(["schtasks", "/End", "/TN", TAREA_SERVIDOR], obligatorio=False)
    if not esperar(lambda: pid_del_servidor() is None, 5):
        pid = pid_del_servidor()
        if pid is not None:
            ejecutar(["taskkill", "/F", "/T", "/PID", str(pid)], obligatorio=False)
    if not esperar(lambda: pid_del_servidor() is None, 5):
        raise RuntimeError(f"No se pudo liberar el puerto {PUERTO}")


def iniciar_servidor():
    ejecutar(["schtasks", "/Run", "/TN", TAREA_SERVIDOR])
    if not esperar(lambda: pid_del_servidor() is not None, 20):
        log(f"El servidor no empezo a escuchar en el puerto {PUERTO}; revisar servidor.log")


def hay_version_nueva():
    ejecutar(["git", "fetch", "origin", RAMA])
    local = ejecutar(["git", "rev-parse", "HEAD"]).strip()
    remoto = ejecutar(["git", "rev-parse", f"origin/{RAMA}"]).strip()
    return local != remoto, local[:7], remoto[:7]


def aplicar_actualizacion():
    ejecutar(["git", "pull", "--ff-only", "origin", RAMA])
    ejecutar([PYTHON, "-m", "pip", "install", "-r", "requirements.txt", "--quiet"])
    ejecutar([PYTHON, "manage.py", "migrate", "--noinput"])
    ejecutar([PYTHON, "manage.py", "collectstatic", "--noinput", "--clear"])


def actualizar_si_corresponde():
    try:
        nueva, local, remoto = hay_version_nueva()
    except Exception as error:
        log(f"No se pudo consultar el repositorio: {error}")
        return

    if not nueva:
        return

    log(f"Version nueva detectada: {local} -> {remoto}")
    try:
        detener_servidor()
        aplicar_actualizacion()
        log("Actualizacion aplicada correctamente")
    except Exception as error:
        log(f"Error al actualizar: {error}")
    finally:
        """
        El servidor se vuelve a levantar aunque la actualizacion haya
        fallado: es preferible que siga corriendo la version anterior a
        dejar al cliente sin sistema.
        """
        iniciar_servidor()
        log("Servidor reiniciado")


def vigilar_servidor():
    if pid_del_servidor() is None:
        log("El servidor no estaba corriendo; se levanta")
        iniciar_servidor()


def main():
    actualizar_si_corresponde()
    vigilar_servidor()


if __name__ == "__main__":
    main()
