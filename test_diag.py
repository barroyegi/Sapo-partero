"""Diagnóstico: reproduce la secuencia real (step_0 en JUMP, luego Kelio)
y vuelca en qué frame/página acabamos, para ver por qué no aparece el calendario.

Solo lee. No envía, modifica ni borra ningún parte.

Uso: python test_diag.py [--con-step0] [--headless]
"""
import sys
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import automation_script as a

KELIO_URL = "http://dc0nproapp029.admon-nas.nasertic.es:8089/open/bwt/portail.jsp"


def dump_frames(driver, etiqueta):
    print(f"\n=== {etiqueta} ===")
    print(f"URL: {driver.current_url}")
    driver.switch_to.default_content()
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    print(f"iframes en el documento principal: {len(iframes)}")

    def info(ctx):
        cal = len(driver.find_elements(By.CSS_SELECTOR, "td.tdCalMois"))
        sem = len(driver.find_elements(By.CSS_SELECTOR, "a[class*='calSemaine']"))
        det = len(driver.find_elements(By.XPATH, "//*[contains(text(), 'Detalle de acumulados')]"))
        inner = len(driver.find_elements(By.TAG_NAME, "iframe"))
        try:
            texto = driver.find_element(By.TAG_NAME, "body").text.strip().replace("\n", " | ")[:200]
        except Exception:
            texto = "(sin body)"
        print(f"  [{ctx}] tdCalMois={cal} calSemaine={sem} 'Detalle de acumulados'={det} iframes_dentro={inner}")
        print(f"      body: {texto}")

    info("principal")
    for i in range(len(iframes)):
        driver.switch_to.default_content()
        frames = driver.find_elements(By.TAG_NAME, "iframe")
        if i >= len(frames):
            break
        src = frames[i].get_attribute("src")
        driver.switch_to.frame(frames[i])
        print(f"  iframe[{i}] src={src}")
        info(f"iframe {i}")
        # Un nivel más de anidamiento
        anidados = driver.find_elements(By.TAG_NAME, "iframe")
        for j in range(len(anidados)):
            driver.switch_to.default_content()
            driver.switch_to.frame(driver.find_elements(By.TAG_NAME, "iframe")[i])
            sub = driver.find_elements(By.TAG_NAME, "iframe")
            if j >= len(sub):
                break
            driver.switch_to.frame(sub[j])
            info(f"iframe {i}.{j}")
    driver.switch_to.default_content()


def kelio_login_y_resultados(driver, config):
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

    time.sleep(3)
    dump_frames(driver, "Tras login en Kelio (antes de Resultados)")

    via = "click"
    try:
        resultados_div = WebDriverWait(driver, 10).until(EC.presence_of_element_located(
            (By.XPATH, "//td[contains(text(), 'Resultados')]/ancestor::div[@type='PortailVignetteLienExec']")))
        driver.execute_script("arguments[0].scrollIntoView(true);", resultados_div)
        time.sleep(1)
        ActionChains(driver).move_to_element(resultados_div).click().perform()
    except Exception as e:
        via = f"fallback driver.get (motivo: {type(e).__name__})"
        driver.get(KELIO_URL + "#resultados")
    print(f"\nNavegación a Resultados vía: {via}")
    time.sleep(5)
    dump_frames(driver, "Tras abrir Resultados")


def main():
    headless = "--headless" in sys.argv
    con_step0 = "--con-step0" in sys.argv

    config = a.load_config()
    if not config:
        print("Error: no se encontró config.json")
        return 1

    driver = a.setup_driver(headless=headless)
    try:
        if con_step0:
            print(">>> Ejecutando step_0 (JUMP, solo lectura)...")
            last = a.step_0_get_last_reported_date(driver)
            print(f">>> step_0 devolvió: {last}")
        else:
            print(">>> Sin step_0: solo Kelio")

        kelio_login_y_resultados(driver, config)
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    sys.exit(main())
