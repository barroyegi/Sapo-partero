"""Prueba de la selección de proyecto/partida en los desplegables de JUMP.

Usa un desplegable simulado: no abre navegador ni toca JUMP.

Uso: python test_seleccion.py
"""
import sys
import numpy as np
import pandas as pd

import automation_script as a


class OpcionFalsa:
    def __init__(self, text):
        self.text = text


class SelectFalso:
    """Imita lo que usa el código de selenium.webdriver.support.ui.Select."""

    def __init__(self, textos):
        self.options = [OpcionFalsa(t) for t in textos]
        self.seleccionado = None

    def select_by_visible_text(self, texto):
        self.seleccionado = texto


OPCIONES_PROYECTO = [
    "-- Seleccione --",
    "AS/0032 · RED NELS MANTENIMIENTO PORTAL WEB_25-26",
    "AS/0041 · PYRENEES4CLIMA",
    "AS/0055 · ENCARGO PACES",
]

# 12.1 va ANTES que 2.1 a propósito: con comparación por subcadena, "2.1"
# casaría con "12.1" y se imputaría a la partida equivocada.
OPCIONES_PARTIDA = [
    "-- Seleccione --",
    "12.1 Gestion",
    "2.10 Difusion",
    "2.1 Analisis",
    "2.2 Desarrollo",
    "3 Coordinacion",
    "6.1 Soporte",
]


def comprobar(descripcion, select_textos, valor, etiqueta, esperado):
    sel = SelectFalso(select_textos)
    logs = []
    ok = a._seleccionar_opcion(sel, valor, etiqueta, logs.append)
    correcto = (sel.seleccionado == esperado)
    estado = "OK " if correcto else "FALLO"
    print(f"[{estado}] {descripcion}: encontrado={ok} seleccionado={sel.seleccionado!r} "
          f"(esperado {esperado!r})")
    for l in logs:
        print(f"        log: {l}")
    return correcto


def main():
    casos = [
        # (descripcion, opciones, valor, etiqueta, esperado)
        # --- Partidas: comparación estricta por código ---
        ("partida float64 2.1", OPCIONES_PARTIDA, np.float64(2.1), "Partida", "2.1 Analisis"),
        ("partida float64 12.1", OPCIONES_PARTIDA, np.float64(12.1), "Partida", "12.1 Gestion"),
        ("partida float64 6.1", OPCIONES_PARTIDA, np.float64(6.1), "Partida", "6.1 Soporte"),
        ("partida float64 2.2", OPCIONES_PARTIDA, np.float64(2.2), "Partida", "2.2 Desarrollo"),
        ("partida entera 3.0", OPCIONES_PARTIDA, np.float64(3.0), "Partida", "3 Coordinacion"),
        ("partida texto '2.1'", OPCIONES_PARTIDA, "2.1", "Partida", "2.1 Analisis"),
        ("partida 2.10 no es 2.1", OPCIONES_PARTIDA, "2.10", "Partida", "2.10 Difusion"),
        ("partida vacía (NaN)", OPCIONES_PARTIDA, np.nan, "Partida", None),
        ("partida inexistente 9.9", OPCIONES_PARTIDA, np.float64(9.9), "Partida", None),

        # --- Proyectos: se admite parecido por encima del umbral ---
        ("proyecto exacto", OPCIONES_PROYECTO, "PYRENEES4CLIMA", "Proyecto",
         "AS/0041 · PYRENEES4CLIMA"),
        ("proyecto con espacio final", OPCIONES_PROYECTO, "ENCARGO PACES ", "Proyecto",
         "AS/0055 · ENCARGO PACES"),
        ("proyecto sin tilde ni mayúsculas", OPCIONES_PROYECTO, "encargo paces", "Proyecto",
         "AS/0055 · ENCARGO PACES"),
        ("proyecto con errata", OPCIONES_PROYECTO, "PYRENEES4CLIMAA", "Proyecto",
         "AS/0041 · PYRENEES4CLIMA"),
        ("proyecto con guion en vez de espacio", OPCIONES_PROYECTO, "RED-NELS", "Proyecto",
         "AS/0032 · RED NELS MANTENIMIENTO PORTAL WEB_25-26"),
        ("proyecto parcial", OPCIONES_PROYECTO, "RED NELS", "Proyecto",
         "AS/0032 · RED NELS MANTENIMIENTO PORTAL WEB_25-26"),
        ("proyecto irreconocible", OPCIONES_PROYECTO, "PROYECTO FANTASMA", "Proyecto", None),
        ("proyecto vacío", OPCIONES_PROYECTO, "", "Proyecto", None),
    ]

    fallos = sum(0 if comprobar(*c) else 1 for c in casos)
    print(f"\n{len(casos) - fallos}/{len(casos)} correctos")
    return 0 if fallos == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
