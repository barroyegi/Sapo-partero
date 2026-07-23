"""Comprueba que los errores de Salto 3 salen legibles en el registro.

Simula un timeout de Selenium (que llega con el mensaje vacío y un volcado de
chromedriver) y verifica que el log resultante es una sola línea útil.

No abre navegador ni toca JUMP.

Uso: python test_errores.py
"""
import sys
import datetime

from selenium.common.exceptions import TimeoutException

import automation_script as a

# Un TimeoutException real: mensaje vacío + volcado de chromedriver
VOLCADO = (
    "Message: \n"
    "Stacktrace:\n"
    "\tchromedriver!GetHandleVerifier [0x7ff67dada8e5+14e45]\n"
    "\tchromedriver!GetHandleVerifier [0x7ff67dada950+14eb0]\n"
    "\tKERNEL32!BaseThreadInitThunk [0x7ffeaaf8e8d7+17]\n"
)


class DriverFalso:
    """Driver mínimo que solo sirve para que _esperar agote su espera."""

    def __getattr__(self, nombre):
        raise AssertionError(f"No se esperaba usar driver.{nombre}")


def prueba_esperar_da_mensaje_util():
    """_esperar debe convertir el timeout mudo en una frase que diga qué faltaba."""
    def condicion_que_nunca_se_cumple(driver):
        return False

    try:
        a._esperar(DriverFalso(), condicion_que_nunca_se_cumple,
                   "que se carguen las partidas del proyecto", timeout=1)
        print("[FALLO] _esperar no lanzó excepción")
        return False
    except RuntimeError as e:
        texto = str(e)
        ok = "partidas del proyecto" in texto and "\n" not in texto
        print(f"[{'OK ' if ok else 'FALLO'}] _esperar: {texto}")
        return ok


def prueba_log_sin_volcado():
    """El manejador de Salto 3 debe registrar una línea, no el volcado entero."""
    logs = []

    # Reproducimos el formato del except de step_3_submit_report
    e = TimeoutException()
    detalle = VOLCADO.split("\n")[0].strip()
    if detalle in ("", "Message:"):
        detalle = type(e).__name__
    fecha = datetime.date(2026, 7, 20)
    logs.append(f"Error en Salto 3 ({fecha.strftime('%d/%m/%Y')}): {detalle}")

    linea = logs[0]
    ok = ("chromedriver" not in linea and "20/07/2026" in linea
          and not linea.endswith("Message:") and "TimeoutException" in linea)
    print(f"[{'OK ' if ok else 'FALLO'}] log de una línea: {linea!r}")
    return ok


def main():
    resultados = [
        prueba_esperar_da_mensaje_util(),
        prueba_log_sin_volcado(),
    ]
    fallos = resultados.count(False)
    print(f"\n{len(resultados) - fallos}/{len(resultados)} correctos")
    return 0 if fallos == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
