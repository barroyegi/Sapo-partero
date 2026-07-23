"""Prueba de navegación del calendario de Kelio.

Hace login en Kelio, abre Resultados y, para cada fecha de la lista FECHAS,
navega el calendario hasta su mes, selecciona su semana, abre 'Detalle de
acumulados' y muestra las horas de ese día.

No toca JUMP y no envía, modifica ni borra ningún parte.

Uso: python test_calendar.py [--headless]
"""
import sys
import time
import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import automation_script as a

FECHAS = [
    datetime.date(2026, 7, 14),
    datetime.date(2026, 6, 22),
    datetime.date(2026, 5, 19),
    datetime.date(2026, 4, 15),
]

KELIO_URL = "http://dc0nproapp029.admon-nas.nasertic.es:8089/open/bwt/portail.jsp"


def _login_and_open_resultados(driver, config):
    """Mismo camino que step_1_scrape_missing_days hasta dejar visible el calendario."""
    driver.get(KELIO_URL + "#index")
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    time.sleep(2)

    try:
        user_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.NAME, "username")))
    except Exception:
        user_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//input[@type='text']")))
    try:
        pass_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.NAME, "password")))
    except Exception:
        pass_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//input[@type='password']")))

    user_input.clear()
    user_input.send_keys(config.get("kelio_user", ""))
    pass_input.clear()
    pass_input.send_keys(config.get("kelio_password", ""))

    try:
        driver.find_element(By.XPATH, "//*[contains(@value, 'Validar') or contains(text(), 'Validar')]").click()
    except Exception:
        driver.find_element(By.XPATH, "//input[@type='submit' and @value='Validar']").click()

    try:
        resultados_div = WebDriverWait(driver, 10).until(EC.presence_of_element_located(
            (By.XPATH, "//td[contains(text(), 'Resultados')]/ancestor::div[@type='PortailVignetteLienExec']")))
        driver.execute_script("arguments[0].scrollIntoView(true);", resultados_div)
        time.sleep(1)
        ActionChains(driver).move_to_element(resultados_div).click().perform()
    except Exception:
        driver.get(KELIO_URL + "#resultados")

    time.sleep(5)
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    if iframes:
        driver.switch_to.frame(iframes[0])


def _volver_al_calendario(driver):
    """Vuelve desde 'Detalle de acumulados' a la vista con el calendario."""
    try:
        back_btn = WebDriverWait(driver, 5).until(EC.presence_of_element_located(
            (By.XPATH, "//a[contains(text(), 'Página anterior')]")))
        driver.execute_script("arguments[0].click();", back_btn)
        time.sleep(3)
    except Exception:
        driver.get(KELIO_URL + "#resultados")
        time.sleep(5)
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        if iframes:
            driver.switch_to.frame(iframes[0])


def _horas_de_fecha(driver, fecha):
    """Navega hasta la semana de la fecha y devuelve las horas de ese día (o None)."""
    iso_year, iso_week, _ = fecha.isocalendar()
    # Mes que muestra esta semana: el del jueves (regla ISO)
    thursday = fecha - datetime.timedelta(days=fecha.weekday()) + datetime.timedelta(days=3)

    if not a._navigate_calendar_to_month(driver, thursday.year, thursday.month):
        print(f"  Aviso: no se pudo navegar hasta {thursday.strftime('%m/%Y')}")
        return None

    # Seleccionar la semana en el calendario
    week_selector = (f"//a[normalize-space()='{iso_week}' and "
                     f"(contains(@class, 'calSemaine') or contains(@class, 'calSemaineSelect'))]")
    week_link = driver.find_elements(By.XPATH, week_selector)
    if not week_link:
        print(f"  Aviso: no se encontró el enlace de la semana {iso_week}")
        return None
    driver.execute_script("arguments[0].click();", week_link[0])
    time.sleep(3)

    # Abrir 'Detalle de acumulados'
    detalle_btn = WebDriverWait(driver, 10).until(EC.presence_of_element_located(
        (By.XPATH, "//*[contains(text(), 'Detalle de acumulados')]")))
    ActionChains(driver).move_to_element(detalle_btn).click().perform()
    time.sleep(3)
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "tr")))

    # Buscar la fila de la fecha (misma extracción que step_1: horas en cells[-3])
    horas = None
    target = fecha.strftime("%d/%m/%Y")
    for row in driver.find_elements(By.TAG_NAME, "tr"):
        try:
            cells = row.find_elements(By.XPATH, "./td")
            if not cells or cells[0].text.strip() != target:
                continue
            if len(cells) >= 3:
                horas = cells[-3].text.strip()
            break
        except Exception:
            continue

    _volver_al_calendario(driver)
    return horas


def main():
    headless = "--headless" in sys.argv

    config = a.load_config()
    if not config:
        print("Error: no se encontró config.json")
        return 1

    fallos = 0
    driver = a.setup_driver(headless=headless)
    try:
        print("Entrando en Kelio...")
        _login_and_open_resultados(driver, config)

        state = a._read_calendar_month_year(driver)
        print(f"Calendario inicial: {state}")
        if not state:
            print("FALLO: no se pudo leer el calendario inicial.")
            return 1

        resultados = []
        for fecha in FECHAS:
            print(f"\nConsultando {fecha.strftime('%d/%m/%Y')} (semana {fecha.isocalendar()[1]})...")
            horas = _horas_de_fecha(driver, fecha)
            resultados.append((fecha, horas))
            if horas is None:
                fallos += 1
            print(f"  Horas: {horas if horas else 'NO ENCONTRADO'}")

        print("\n--- Resumen ---")
        for fecha, horas in resultados:
            print(f"{fecha.strftime('%d/%m/%Y')}: {horas if horas else 'NO ENCONTRADO'}")
        print(f"\nResultado: {'TODO OK' if fallos == 0 else f'{fallos} fecha(s) sin horas'}")
        return 0 if fallos == 0 else 1
    finally:
        driver.quit()


if __name__ == "__main__":
    sys.exit(main())
