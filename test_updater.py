"""Pruebas del sistema de actualizaciones.

Comprueba la comparacion de versiones y, sobre todo, que una descarga
defectuosa NUNCA deja la instalacion rota.

Trabaja en una carpeta temporal: no toca la instalacion real ni la red.

Uso: python test_updater.py
"""
import json
import os
import shutil
import sys
import tempfile

import updater

CODIGO_BUENO = "# fichero de prueba\n" + "x = 1\n" * 100      # > 500 bytes
CODIGO_ROTO = "# fichero de prueba\ndef roto(:\n" + "y = 2\n" * 100
HTML_ERROR = "<!DOCTYPE html><html><body>404: Not Found</body></html>" + " " * 600


def comprobar(descripcion, obtenido, esperado):
    ok = obtenido == esperado
    print(f"[{'OK ' if ok else 'FALLO'}] {descripcion}: {obtenido!r} (esperado {esperado!r})")
    return ok


def pruebas_version():
    casos = [
        ("1.2.1 mas nueva que 1.2.0", ("1.2.1", "1.2.0"), True),
        ("1.2.0 no mas nueva que 1.2.0", ("1.2.0", "1.2.0"), False),
        ("1.1.9 no mas nueva que 1.2.0", ("1.1.9", "1.2.0"), False),
        ("2.0.0 mas nueva que 1.9.9", ("2.0.0", "1.9.9"), True),
        ("1.2 igual a 1.2.0", ("1.2", "1.2.0"), False),
        ("1.10.0 mas nueva que 1.9.0", ("1.10.0", "1.9.0"), True),
        ("version basura no actualiza", ("no-es-version", "1.2.0"), False),
        ("version vacia no actualiza", ("", "1.2.0"), False),
    ]
    return [comprobar(d, updater.es_mas_nueva(*args), esp) for d, args, esp in casos]


class DescargaFalsa:
    """Sustituye a updater._descargar para no tocar la red."""

    def __init__(self, contenidos):
        self.contenidos = contenidos

    def __call__(self, url, timeout=None):
        for clave, valor in self.contenidos.items():
            if url.endswith(clave):
                if valor is None:
                    raise ConnectionError("fallo de red simulado")
                return valor.encode("utf-8")
        raise ConnectionError(f"no simulado: {url}")


def escenario(contenidos, ficheros=("automation_script.py",)):
    """Monta una instalacion falsa y aplica una actualizacion. Devuelve (ok, contenido_final, logs)."""
    tmp = tempfile.mkdtemp(prefix="sapo_test_")
    original = "CONTENIDO ORIGINAL INTACTO\n"
    try:
        for f in ficheros:
            with open(os.path.join(tmp, f), "w", encoding="utf-8") as fh:
                fh.write(original)

        # Redirigimos el directorio de la app y la descarga
        app_dir_real, descargar_real = updater.app_dir, updater._descargar
        updater.app_dir = lambda: tmp
        updater._descargar = DescargaFalsa(contenidos)
        try:
            logs = []
            info = {"version": "9.9.9", "ficheros": list(ficheros)}
            ok = updater.descargar_actualizacion(info, log=logs.append)
        finally:
            updater.app_dir, updater._descargar = app_dir_real, descargar_real

        with open(os.path.join(tmp, ficheros[0]), "r", encoding="utf-8") as fh:
            final = fh.read()
        return ok, final, logs, original
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def pruebas_instalacion():
    res = []

    # 1. Descarga correcta: se instala
    ok, final, logs, orig = escenario({"automation_script.py": CODIGO_BUENO})
    res.append(comprobar("descarga correcta se instala", (ok, final == CODIGO_BUENO), (True, True)))

    # 2. Codigo con error de sintaxis: se rechaza y NO se toca el fichero
    ok, final, logs, orig = escenario({"automation_script.py": CODIGO_ROTO})
    res.append(comprobar("codigo roto se rechaza", ok, False))
    res.append(comprobar("  y el original queda intacto", final, orig))

    # 3. Pagina HTML de error en vez del .py: se rechaza
    ok, final, logs, orig = escenario({"automation_script.py": HTML_ERROR})
    res.append(comprobar("HTML de error se rechaza", ok, False))
    res.append(comprobar("  y el original queda intacto", final, orig))

    # 4. Fichero truncado (demasiado pequeno): se rechaza
    ok, final, logs, orig = escenario({"automation_script.py": "x=1\n"})
    res.append(comprobar("descarga truncada se rechaza", ok, False))
    res.append(comprobar("  y el original queda intacto", final, orig))

    # 5. Corte de red a mitad: se rechaza
    ok, final, logs, orig = escenario({"automation_script.py": None})
    res.append(comprobar("fallo de red se rechaza", ok, False))
    res.append(comprobar("  y el original queda intacto", final, orig))

    # 6. Si un fichero del lote viene roto, NINGUNO se instala
    ok, final, logs, orig = escenario(
        {"automation_script.py": CODIGO_BUENO, "gui_app.py": CODIGO_ROTO},
        ficheros=("automation_script.py", "gui_app.py"))
    res.append(comprobar("un fichero roto cancela todo el lote", ok, False))
    res.append(comprobar("  y el bueno tampoco se escribe", final, orig))

    # 7. Ruta fuera de la lista blanca: se ignora
    ok, final, logs, orig = escenario({"automation_script.py": CODIGO_BUENO})
    tmp = tempfile.mkdtemp(prefix="sapo_test_")
    try:
        app_dir_real, descargar_real = updater.app_dir, updater._descargar
        updater.app_dir = lambda: tmp
        updater._descargar = DescargaFalsa({"evil.py": CODIGO_BUENO})
        try:
            logs = []
            info = {"version": "9.9.9", "ficheros": ["../../evil.py"]}
            ok = updater.descargar_actualizacion(info, log=logs.append)
        finally:
            updater.app_dir, updater._descargar = app_dir_real, descargar_real
        ignorado = any("no está en la lista" in l for l in logs)
        res.append(comprobar("ruta fuera de la lista blanca se rechaza", (ok, ignorado), (False, True)))
        res.append(comprobar("  y no se crea nada fuera", os.path.exists(os.path.join(tmp, "evil.py")), False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return res


def prueba_version_json():
    """El version.json del repo debe ser valido y cuadrar con updater.VERSION."""
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.json")
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            info = json.load(f)
    except Exception as e:
        print(f"[FALLO] version.json no se puede leer: {e}")
        return [False]

    res = [comprobar("version.json coincide con updater.VERSION",
                     info.get("version"), updater.VERSION)]
    validos = all(f in updater.FICHEROS_ACTUALIZABLES for f in info.get("ficheros", []))
    res.append(comprobar("  todos sus ficheros estan en la lista blanca", validos, True))
    return res


def main():
    print("--- Comparacion de versiones ---")
    r = pruebas_version()
    print("\n--- Instalacion y seguridad ---")
    r += pruebas_instalacion()
    print("\n--- version.json ---")
    r += prueba_version_json()

    fallos = r.count(False)
    print(f"\n{len(r) - fallos}/{len(r)} correctos")
    return 0 if fallos == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
