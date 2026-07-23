"""Prueba del flujo real de lectura: step_0 (JUMP) + step_1 (Kelio).

step_1 solo lee Kelio: devuelve la lista de días pendientes con sus horas.
No envía, modifica ni borra ningún parte en JUMP.

Uso: python test_step1.py [YYYY-MM-DD] [--headless]
     La fecha es el 'último reporte' simulado (por defecto, 90 días atrás).
"""
import sys
import datetime

import automation_script as a


def main():
    headless = "--headless" in sys.argv
    desde = datetime.date.today() - datetime.timedelta(days=90)
    for arg in sys.argv[1:]:
        if arg.startswith("--"):
            continue
        try:
            desde = datetime.datetime.strptime(arg, "%Y-%m-%d").date()
        except ValueError:
            pass

    driver = a.setup_driver(headless=headless)
    try:
        print(">>> step_0 (JUMP, solo lectura)")
        real = a.step_0_get_last_reported_date(driver)
        print(f">>> Último reporte real: {real}")
        print(f">>> Simulando último reporte: {desde} (para forzar varios meses)\n")

        dias = a.step_1_scrape_missing_days(driver, desde)

        print(f"\n--- Días encontrados: {len(dias)} ---")
        for fecha, horas, modo in dias:
            print(f"{fecha.strftime('%d/%m/%Y')}  {horas:>5}  {modo}")
        return 0 if dias else 1
    finally:
        driver.quit()


if __name__ == "__main__":
    sys.exit(main())
