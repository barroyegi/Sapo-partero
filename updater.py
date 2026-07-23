"""Comprobación y descarga de actualizaciones desde GitHub.

Solo se actualizan los ficheros .py de la aplicación (unos 80 KB): el intérprete
de Python empaquetado no se toca nunca. Windows no bloquea los .py mientras
Python corre, así que se sobrescriben sin problema y el cambio entra al
siguiente arranque.

Se usa raw.githubusercontent.com en vez de la API de GitHub porque la API
limita a 60 peticiones/hora por IP y, tras el NAT corporativo, todos los
usuarios comparten la misma IP.

No requiere dependencias: urllib es de la biblioteca estándar.
"""

import json
import os
import shutil
import sys
import urllib.request
import urllib.error

# --- Versión actual de la aplicación ---
# Subir este número al publicar cambios, y reflejarlo en el version.json del repo.
VERSION = "1.2.0"

# --- Repositorio de GitHub (rellenar con el repo real) ---
GITHUB_USER = "barroyegi"
GITHUB_REPO = "Sapo-partero"
GITHUB_RAMA = "main"

BASE_RAW = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_RAMA}"

# Lista blanca: solo estos ficheros se pueden sobrescribir. Impide que un
# version.json manipulado escriba en rutas arbitrarias (../../algo.py).
FICHEROS_ACTUALIZABLES = ("automation_script.py", "gui_app.py", "updater.py")

# Un .py de la aplicación nunca es tan pequeño: si lo es, la descarga vino mal.
TAMANO_MINIMO = 500

TIMEOUT = 10


def app_dir():
    """Directorio donde vive la aplicación (o el script en desarrollo)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _tupla_version(v):
    """'1.2.0' -> (1, 2, 0). Devuelve () si el formato no es válido."""
    try:
        return tuple(int(p) for p in str(v).strip().split("."))
    except (ValueError, AttributeError):
        return ()


def es_mas_nueva(remota, local):
    """True si la versión remota es posterior a la local."""
    a, b = _tupla_version(remota), _tupla_version(local)
    if not a or not b:
        return False
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    return a > b


def _descargar(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": f"SapoPartero/{VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def esta_configurado():
    """False mientras no se haya puesto el usuario real de GitHub."""
    return "CAMBIAR" not in GITHUB_USER


def comprobar_actualizacion(log=print):
    """Consulta si hay versión nueva.

    Devuelve el diccionario de version.json si la hay, o None. Nunca lanza
    excepción: sin conexión, la aplicación debe seguir funcionando igual.
    """
    if not esta_configurado():
        return None

    if getattr(sys, 'frozen', False):
        # En el .exe el código va empaquetado dentro: reemplazar los .py no haría nada.
        return None

    try:
        datos = _descargar(f"{BASE_RAW}/version.json")
        info = json.loads(datos.decode("utf-8"))
    except urllib.error.URLError:
        return None          # Sin conexión o GitHub inaccesible: silencio
    except Exception as e:
        log(f"No se pudo comprobar si hay actualizaciones: {e}")
        return None

    remota = info.get("version", "")
    if es_mas_nueva(remota, VERSION):
        info["_version_local"] = VERSION
        return info
    return None


def descargar_actualizacion(info, log=print):
    """Descarga y aplica la actualización. Devuelve True si se instaló.

    Se descarga y valida TODO antes de tocar ningún fichero, y se guarda una
    copia de la versión anterior para poder volver atrás.
    """
    destino = app_dir()

    # Solo ficheros de la lista blanca: un version.json manipulado no puede
    # hacernos escribir fuera del directorio de la aplicación.
    pedidos = info.get("ficheros") or list(FICHEROS_ACTUALIZABLES)
    ficheros = [f for f in pedidos if f in FICHEROS_ACTUALIZABLES]
    ignorados = [f for f in pedidos if f not in FICHEROS_ACTUALIZABLES]
    for f in ignorados:
        log(f"⚠ Se ignora '{f}': no está en la lista de ficheros actualizables.")
    if not ficheros:
        log("La actualización no indica ningún fichero válido.")
        return False

    # --- 1. Descargar y validar en memoria, sin tocar el disco ---
    nuevos = {}
    for nombre in ficheros:
        try:
            datos = _descargar(f"{BASE_RAW}/{nombre}")
        except Exception as e:
            log(f"Error al descargar {nombre}: {e}")
            return False

        if len(datos) < TAMANO_MINIMO:
            log(f"Error: {nombre} llegó incompleto ({len(datos)} bytes). Se cancela.")
            return False

        try:
            texto = datos.decode("utf-8")
            compile(texto, nombre, "exec")   # Detecta descargas truncadas o corruptas
        except (UnicodeDecodeError, SyntaxError) as e:
            log(f"Error: {nombre} no es Python válido ({e}). Se cancela la actualización.")
            return False

        nuevos[nombre] = texto
        log(f"Descargado {nombre} ({len(datos):,} bytes)")

    # --- 2. Copia de seguridad de la versión actual ---
    copia = os.path.join(destino, f"version_anterior_{info.get('_version_local', VERSION)}")
    try:
        os.makedirs(copia, exist_ok=True)
        for nombre in nuevos:
            origen = os.path.join(destino, nombre)
            if os.path.exists(origen):
                shutil.copy2(origen, os.path.join(copia, nombre))
        log(f"Copia de la versión anterior en: {os.path.basename(copia)}")
    except Exception as e:
        log(f"No se pudo hacer la copia de seguridad: {e}. Se cancela por precaución.")
        return False

    # --- 3. Escribir los ficheros nuevos ---
    escritos = []
    try:
        for nombre, texto in nuevos.items():
            with open(os.path.join(destino, nombre), "w", encoding="utf-8") as f:
                f.write(texto)
            escritos.append(nombre)
    except Exception as e:
        log(f"Error al escribir {nombre}: {e}. Restaurando la versión anterior...")
        for n in escritos:
            try:
                shutil.copy2(os.path.join(copia, n), os.path.join(destino, n))
            except Exception:
                pass
        log(f"Restaurado. Si algo quedó mal, los ficheros originales están en "
            f"{os.path.basename(copia)}")
        return False

    log(f"Actualizado a la versión {info.get('version')}. Reinicia la aplicación.")
    return True


def texto_cambios(info):
    """Changelog en texto para mostrar en el diálogo."""
    cambios = info.get("cambios") or []
    if isinstance(cambios, str):
        return cambios
    return "\n".join(f"  • {c}" for c in cambios)
