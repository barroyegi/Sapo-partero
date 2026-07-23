import time
import datetime
import os
import sys
import random
import re
import difflib
import unicodedata
import subprocess
import json
import traceback
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

CONFIG_FILE = "config.json"
PROJECTS_FILE = "projects.xlsx"

def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        # Un espacio sobrante al copiar y pegar las credenciales hace fallar el login
        return {k: v.strip() if isinstance(v, str) else v for k, v in config.items()}
    except FileNotFoundError:
        return None

def setup_driver(headless=True):
    options = webdriver.ChromeOptions()
    options.add_argument('--ignore-certificate-errors')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-background-networking')
    if headless:
        options.add_argument('--headless=new')
        options.add_argument('--window-size=1920,1080')
    driver = webdriver.Chrome(options=options)
    return driver

def step_0_get_last_reported_date(driver, log_func=print):
    log_func("\n--- Preparando: Obtener fecha de último reporte ---")
    config = load_config()
    if not config: 
        log_func("Error: Config not found")
        return None
    
    try:
        driver.get("https://jumpnasuvinsa.nasertic.es/Login.aspx")
        
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "MainContent_LoginUser_UserName")))
        driver.find_element(By.ID, "MainContent_LoginUser_UserName").send_keys(config.get("jump_user", ""))
        driver.find_element(By.ID, "Password").send_keys(config.get("jump_password", ""))
        driver.find_element(By.ID, "MainContent_LoginUser_Button1").click()
        
        partes_btn = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'PARTES DE TRABAJO')]")))
        driver.execute_script("arguments[0].click();", partes_btn)
        
        diario_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Parte de trabajo Diario')]")))
        driver.execute_script("arguments[0].click();", diario_btn)
        
        time.sleep(3)
        
        last_date = None
        try:
            tables = driver.find_elements(By.TAG_NAME, "table")
            for table in tables:
                rows = table.find_elements(By.TAG_NAME, "tr")
                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    for cell in cells:
                        text = cell.text.strip()
                        try:
                            date_obj = datetime.datetime.strptime(text, "%d/%m/%Y").date()
                            if last_date is None or date_obj > last_date:
                                last_date = date_obj
                        except:
                            pass
                            
            if last_date:
                log_func(f"Día del último reporte: {last_date.strftime('%d/%m/%Y')}")
                return last_date
            else:
                log_func("No se han encontrado fechas anteriores. Se probará con los últimos 7 dias.")
                return datetime.date.today() - datetime.timedelta(days=7)
                
        except Exception as e:
            log_func(f"Error inspecting tables: {e}")
            return None

    except Exception as e:
        log_func(f"Error in Step 0: {e}")
        return None

KELIO_URL = "http://dc0nproapp029.admon-nas.nasertic.es:8089/open/bwt/portail.jsp"

_MESES_ES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
}

def _switch_to_kelio_calendar_frame(driver, log_func=print, timeout=30):
    """Sitúa el driver en el frame que contiene el calendario de Kelio.

    El portal crea varios iframes (alguno vacío) y su orden no es fijo, así que
    se busca el que realmente tiene el calendario en vez de asumir el primero.
    Devuelve True si lo encuentra.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        driver.switch_to.default_content()
        # Puede estar en el documento principal (sin iframes)
        if driver.find_elements(By.CSS_SELECTOR, "td.tdCalMois"):
            return True
        n_frames = len(driver.find_elements(By.TAG_NAME, "iframe"))
        for i in range(n_frames):
            driver.switch_to.default_content()
            frames = driver.find_elements(By.TAG_NAME, "iframe")
            if i >= len(frames):
                break
            try:
                driver.switch_to.frame(frames[i])
            except Exception:
                continue
            if driver.find_elements(By.CSS_SELECTOR, "td.tdCalMois"):
                return True
        time.sleep(1)

    driver.switch_to.default_content()
    log_func("No se encontró el frame con el calendario de Kelio.")
    return False


def _open_kelio_resultados(driver, log_func=print):
    """Abre la vista 'Resultados' de Kelio y deja el driver en el frame del calendario."""
    driver.switch_to.default_content()
    try:
        resultados_div = WebDriverWait(driver, 10).until(EC.presence_of_element_located(
            (By.XPATH, "//td[contains(text(), 'Resultados')]/ancestor::div[@type='PortailVignetteLienExec']")))
        driver.execute_script("arguments[0].scrollIntoView(true);", resultados_div)
        time.sleep(1)
        ActionChains(driver).move_to_element(resultados_div).click().perform()
    except Exception:
        driver.get(KELIO_URL + "#resultados")
    time.sleep(3)
    return _switch_to_kelio_calendar_frame(driver, log_func)


def _read_calendar_month_year(driver, log_func=print):
    """Lee el (mes, año) mostrado en el calendario de Kelio. Devuelve None si no se puede."""
    try:
        month_text = driver.find_element(By.CSS_SELECTOR, "td.tdCalMois").text.strip().lower()
        # Búsqueda por subcadena: tolera que la celda incluya las flechas u otros caracteres
        month = next((num for name, num in _MESES_ES.items() if name in month_text), 0)
        year_els = driver.find_elements(By.CSS_SELECTOR, "td.tdCalAnnee")
        year_text = next((el.text.strip() for el in year_els if el.text.strip().isdigit()), None)
        if not month or not year_text:
            log_func(f"No se pudo interpretar el mes/año del calendario (mes='{month_text}', año='{year_text}').")
            return None
        return month, int(year_text)
    except Exception as e:
        log_func(f"No se pudo leer el mes actual del calendario: {e}")
        return None


def _click_calendar_arrow(driver, unit, direction):
    """Clica la flecha anterior/siguiente del calendario de Kelio.

    unit: 'mes' o 'anno'. direction: -1 (anterior) o +1 (siguiente).
    Devuelve True si se pudo clicar.
    """
    if unit == 'mes':
        titles = ['Mes anterior'] if direction < 0 else ['Mes siguiente']
        cell_class = 'tdCalMois'
    else:
        titles = ['Año anterior', 'Ano anterior'] if direction < 0 else ['Año siguiente', 'Ano siguiente']
        cell_class = 'tdCalAnnee'

    # 1) Por título del enlace o de la imagen que contiene
    for t in titles:
        els = driver.find_elements(
            By.XPATH,
            f"//a[contains(@title, '{t}')] | //img[contains(@title, '{t}')]/ancestor::a[1]")
        if els:
            driver.execute_script("arguments[0].click();", els[0])
            return True

    # 2) Alternativa: primera/última <a> de la fila que contiene la celda del mes/año
    rows = driver.find_elements(By.XPATH, f"//td[contains(@class, '{cell_class}')]/ancestor::tr[1]")
    for row in rows:
        links = row.find_elements(By.TAG_NAME, "a")
        if len(links) >= 2:
            driver.execute_script("arguments[0].click();", links[0] if direction < 0 else links[-1])
            return True
    return False


def _navigate_calendar_to_month(driver, target_year, target_month, log_func=print):
    """Navega el calendario de Kelio hasta el mes/año indicado.

    Usa las flechas junto al año para saltos de más de 12 meses y las flechas
    junto al mes para el resto. Devuelve True si el calendario quedó en el
    mes pedido.
    """
    # Vía rápida: la función JS del propio calendario (mes 0-based, la misma
    # que usan las flechas en su onclick) permite saltar a cualquier mes/año.
    try:
        driver.execute_script("fcChangerCalendrierMois(arguments[0], arguments[1]);",
                              target_month - 1, target_year)
        time.sleep(1.5)
        if _read_calendar_month_year(driver, log_func) == (target_month, target_year):
            return True
    except Exception:
        pass  # La función no existe o falló: seguimos con las flechas

    for _ in range(80):
        state = _read_calendar_month_year(driver, log_func)
        if not state:
            return False
        current_month, current_year = state

        diff = (target_year * 12 + target_month) - (current_year * 12 + current_month)
        if diff == 0:
            return True

        direction = 1 if diff > 0 else -1
        clicked = False
        if abs(diff) > 12:
            clicked = _click_calendar_arrow(driver, 'anno', direction)
        if not clicked:
            clicked = _click_calendar_arrow(driver, 'mes', direction)
        if not clicked:
            log_func("No se encontró la flecha de navegación del calendario.")
            return False
        time.sleep(1.5)

    log_func(f"No se pudo llegar a {target_month:02d}/{target_year} en el calendario.")
    return False


def step_1_scrape_missing_days(driver, last_reported_date, log_func=print):
    log_func("\n--- Salto 1: Mirando horas en Kelio ---")
    config = load_config()
    if not config: return []
    
    missing_days_data = [] 
    today = datetime.date.today()
    
    try:
        driver.get(KELIO_URL + "#index")

        # Login
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
        
        try:
            user_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.NAME, "username")))
        except:
            user_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//input[@type='text']")))
            
        try:
            pass_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.NAME, "password")))
        except:
            pass_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//input[@type='password']")))

        try:
            user_input.clear()
            user_input.send_keys(config.get("kelio_user", ""))
        except:
            driver.execute_script("arguments[0].value = arguments[1];", user_input, config.get("kelio_user", ""))
        
        try:
            pass_input.clear()
            pass_input.send_keys(config.get("kelio_password", ""))
        except:
            driver.execute_script("arguments[0].value = arguments[1];", pass_input, config.get("kelio_password", ""))
        
        try:
            driver.find_element(By.XPATH, "//*[contains(@value, 'Validar') or contains(text(), 'Validar')]").click()
        except:
            driver.find_element(By.XPATH, "//input[@type='submit' and @value='Validar']").click()

        # Comprobar que el login ha funcionado: si no, el resto falla con errores confusos
        time.sleep(3)
        if "authenticationFailure" in driver.current_url or \
                driver.find_elements(By.XPATH, "//*[contains(text(), 'Informaciones incorrectas')]"):
            log_func("Error: usuario o contraseña de Kelio incorrectos. "
                     "Revísalos en el paso 1 (Credenciales). Los de JUMP son independientes.")
            return []

        # 1. Navigate to "Resultados" (Initial navigation)
        if not _open_kelio_resultados(driver, log_func):
            log_func("No se pudo abrir la vista de Resultados de Kelio.")
            return []

        # --- WEEK NAVIGATION LOOP ---
        # Empezamos desde el lunes de la semana del último reporte para asegurar que cubrimos la semana entera
        current_check_date = last_reported_date - datetime.timedelta(days=last_reported_date.weekday())
        processed_dates = set()

        while current_check_date < today:
            iso_year, iso_week, _ = current_check_date.isocalendar()

            # 2. Navegar al mes que muestra esta semana (el mes del jueves de la semana, regla ISO)
            thursday = current_check_date + datetime.timedelta(days=3)
            if not _navigate_calendar_to_month(driver, thursday.year, thursday.month, log_func):
                log_func(f"Aviso: no se pudo navegar el calendario hasta {thursday.strftime('%m/%Y')}; "
                         "se intentará con el mes visible.")

            # 3. Select Week in Calendar (BEFORE clicking Detalle)
            try:
                week_selector = f"//a[normalize-space()='{iso_week}' and (contains(@class, 'calSemaine') or contains(@class, 'calSemaineSelect'))]"
                week_link = driver.find_elements(By.XPATH, week_selector)

                if week_link:
                    driver.execute_script("arguments[0].click();", week_link[0])
                    time.sleep(3)
                else:
                    log_func(f"No se encontró el enlace de la semana {iso_week} en el calendario.")
            except Exception as e:
                log_func(f"Error al seleccionar la semana {iso_week}: {e}")

            # 4. Click "Detalle de acumulados"
            try:
                detalle_btn = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Detalle de acumulados')]")))
                actions = ActionChains(driver)
                actions.move_to_element(detalle_btn).click().perform()
            except Exception as e:
                log_func(f"No he podido clicar en 'Detalle de acumulados': {e}")

            # Esperar a que la tabla se cargue
            time.sleep(3)
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "tr")))

            # 5. Scrape the table
            rows = driver.find_elements(By.TAG_NAME, "tr")
            for i in range(len(rows)):
                try:
                    rows = driver.find_elements(By.TAG_NAME, "tr")
                    if i >= len(rows): break
                    row = rows[i]
                    
                    cells = row.find_elements(By.XPATH, "./td")
                    if not cells: continue
                    
                    cell_text = cells[0].text.strip()
                    try:
                        row_date = datetime.datetime.strptime(cell_text, "%d/%m/%Y").date()
                        
                        if (last_reported_date is None or row_date > last_reported_date) and row_date < today and row_date not in processed_dates:
                            if row_date.weekday() >= 5: continue # Saltar findes
                                
                            if len(cells) >= 3:
                                extracted_time = cells[-3].text.strip()
                                # Se salta los dias con 0:00 o 00:00 (vacaciones)
                                if not extracted_time or extracted_time in ["00:00", "0:00", "00:0", "0:0"]: 
                                    continue
                                
                                # --- Detección de vacaciones por falta de fichajes ---
                                # Las celdas de fichajes son las que contienen una tabla anidada
                                table_cells = [c for c in cells if len(c.find_elements(By.TAG_NAME, "table")) > 0]
                                # Comprobamos si alguna de las primeras 4 celdas de fichaje tiene texto
                                clock_in_values = [c.text.strip() for c in table_cells[:4]]
                                has_any_clock_in = any(val for val in clock_in_values)
                                
                                if not has_any_clock_in:
                                    log_func(f"Día de vacaciones detectado (sin fichajes): {row_date}. Saltando.")
                                    continue
                                
                                work_mode = "Presencial"
                                try:
                                    if len(row.find_elements(By.XPATH, ".//img[@title='Presencia intranet']")) == 4:
                                        work_mode = "Teletrabajo"
                                except: pass
                                
                                missing_days_data.append((row_date, extracted_time, work_mode))
                                processed_dates.add(row_date)
                                log_func(f"Día encontrado: {row_date} ({extracted_time})")
                    except ValueError:
                        continue
                except Exception:
                    continue
            
            # 5. Volver a la página anterior para ver el calendario de nuevo
            try:
                # El usuario indica que este botón vuelve a la vista del calendario
                back_btn = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'Página anterior')]")))
                driver.execute_script("arguments[0].click();", back_btn)
                time.sleep(3) # Esperar a que cargue el calendario
            except:
                log_func("No se encontró el botón 'Página anterior'.")

            # Si el calendario no está visible, rehacemos el camino desde el portal
            if not driver.find_elements(By.CSS_SELECTOR, "td.tdCalMois"):
                log_func("Calendario no visible, volviendo a Resultados...")
                driver.get(KELIO_URL + "#index")
                time.sleep(3)
                if not _open_kelio_resultados(driver, log_func):
                    log_func("No se pudo recuperar el calendario; se detiene el escaneo.")
                    break

            # Pasar a la siguiente semana
            current_check_date += datetime.timedelta(days=7)

        return sorted(missing_days_data, key=lambda x: x[0])

    except Exception as e:
        log_func(f"Error en Salto 1: {e}")
        log_func(traceback.format_exc())
        return []

def step_2_find_project(extracted_time, report_date, log_func=print):
    log_func("\n--- Salto 2: Eligiendo proyecto ---")
    try:
        if not os.path.exists(PROJECTS_FILE):
            log_func("No he encontrado el documento..")
            return None, None, 0, 0, None

        df = pd.read_excel(PROJECTS_FILE)
        
        h, m = map(int, extracted_time.split(':'))
        hours_decimal = h + m / 60.0
        
        if 'Available' not in df.columns:
            df['Available'] = df['Total Hours'] - df['Executed Hours']
            
        # Asegura que la columna 'Fecha límite' existe
        if 'Fecha límite' not in df.columns:
            df['Fecha límite'] = None
            df.to_excel(PROJECTS_FILE, index=False)
            log_func("Columna 'Fecha límite' añadida al Excel.")
            
        # Filtra por Fecha límite si la columna existe
        if 'Fecha límite' in df.columns:
            # Convierte a objetos datetime para la comparación, manejando errores/valores vacíos
            df['Fecha límite'] = pd.to_datetime(df['Fecha límite'], dayfirst=True, errors='coerce')
            
            # Mantiene las filas donde Fecha límite es NaN (sin caducidad) O Fecha límite >= fecha del reporte
            # Se utiliza una máscara para filtrar
            report_timestamp = pd.Timestamp(report_date)
            mask = (df['Fecha límite'].isna()) | (df['Fecha límite'] >= report_timestamp)
            eligible = df[mask & (df['Available'] >= hours_decimal)]
        else:
            eligible = df[df['Available'] >= hours_decimal]
        
        if eligible.empty:
            log_func("No he encontrado proyectos con horas suficientes (o vigentes)!")
            return None, None, h, m, df
            
        # Selección aleatoria ponderada por 'Total Hours' y fecha límite
        # Proyectos más grandes y con fecha límite cercana tienen más probabilidad
        try:
            # Peso base de 'Total Hours'
            base_weights = eligible['Total Hours'].fillna(0).clip(lower=0)
            
            # Peso de urgencia
            urgency_weights = pd.Series(1.0, index=eligible.index)
            
            if 'Fecha límite' in df.columns:
                def calculate_urgency(row):
                    if pd.isna(row['Fecha límite']):
                        return 1.0 
                    
                    # Calcula los dias restantes
                    deadline = row['Fecha límite']
                    # Asegura que la fecha límite es un objeto de fecha
                    if isinstance(deadline, pd.Timestamp):
                        deadline = deadline.date()
                        
                    days_remaining = (deadline - report_date).days
                    
                    if days_remaining < 0: return 0.0 # Se filtra por si acaso
                    
                    # Fórmula de urgencia: Mayor puntuación para menos días restantes
                    # +1 para evitar división por cero
                    # Ejemplo: 0 días -> 101, 9 días -> 11, 99 días -> 2
                    return 1.0 + (100.0 / (days_remaining + 1.0))

                urgency_weights = eligible.apply(calculate_urgency, axis=1)
            
            final_weights = base_weights * urgency_weights
            
            if final_weights.sum() == 0:
                selected = eligible.sample(n=1).iloc[0]
            else:
                selected = eligible.sample(n=1, weights=final_weights).iloc[0]
        except Exception as e:
            log_func(f"Error en selección ponderada, usando aleatorio simple: {e}")
            selected = eligible.sample(n=1).iloc[0]

        log_func(f"Seleccionado: {selected['Project Name']} {selected['Partida']} (Total: {selected['Total Hours']}, Available: {selected['Available']:.2f})")
        return selected['Project Name'], selected['Partida'], h, m, df

    except Exception as e:
        log_func(f"Error en Salto 2: {e}")
        return None, None, 0, 0, None

def _candidatos_texto(valor):
    """Formas de texto plausibles de un valor leído del Excel.

    Las partidas llegan como número (2.1 -> numpy.float64, sin .lower()), y los
    nombres pueden traer espacios sobrantes. Un 3.0 puede figurar como '3' o '3.0'.
    """
    if valor is None:
        return []
    try:
        if pd.isna(valor):
            return []
    except (TypeError, ValueError):
        pass
    if isinstance(valor, (int, float)):
        f = float(valor)
        if f.is_integer():
            return [str(int(f)), f"{f:.1f}"]
        return [repr(f).strip()]
    return [str(valor).strip()]


# Parecido mínimo (0-1) para dar por bueno un proyecto cuyo nombre no es exacto.
UMBRAL_SIMILITUD = 0.75


def _normalizar(texto):
    """Minúsculas, sin acentos ni puntuación y con los espacios colapsados."""
    t = unicodedata.normalize('NFKD', str(texto).lower())
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r'[^a-z0-9]+', ' ', t)
    return ' '.join(t.split())


def _similitud(buscado, opcion):
    """Cuánto se parece 'buscado' al texto de una opción del desplegable (0-1)."""
    b, o = _normalizar(buscado), _normalizar(opcion)
    if not b or not o:
        return 0.0
    if b == o:
        return 1.0
    if b in o or o in b:
        return 0.95

    ratio = difflib.SequenceMatcher(None, b, o).ratio()
    # Cobertura de palabras: 'RED NELS' dentro de 'AS/0032 · RED NELS MANTENIMIENTO...'
    palabras = b.split()
    comunes = sum(1 for p in palabras if p in o.split())
    cobertura = comunes / len(palabras) if palabras else 0.0
    return max(ratio, cobertura * 0.9)


def _coincide_codigo(codigo, texto):
    """True si 'codigo' aparece como código independiente en 'texto'.

    Evita que la partida 2.1 case con '12.1' o con '2.10'.
    """
    patron = r'(?<![\d.])' + re.escape(codigo) + r'(?![\d.])'
    return re.search(patron, texto) is not None


def _seleccionar_opcion(select, valor, etiqueta, log_func=print, umbral=UMBRAL_SIMILITUD):
    """Selecciona en el desplegable la opción que corresponde al valor dado.

    Las partidas (códigos como 2.1) se comparan de forma estricta. Los nombres
    admiten parecido: se elige el más similar siempre que llegue al umbral de
    confianza. Devuelve True si se ha seleccionado algo.
    """
    candidatos = [c for c in _candidatos_texto(valor) if c]
    if not candidatos:
        log_func(f"⚠ {etiqueta}: valor vacío o no válido en el Excel.")
        return False

    # 1. Códigos numéricos: coincidencia exacta, sin parecidos
    numericos = [c for c in candidatos if re.fullmatch(r'[\d.]+', c)]
    if numericos:
        for opt in select.options:
            if any(_coincide_codigo(c, opt.text) for c in numericos):
                select.select_by_visible_text(opt.text)
                return True

    # 2. Nombres: nos quedamos con el más parecido
    mejor_opt, mejor_sim = None, 0.0
    for opt in select.options:
        sim = max(_similitud(c, opt.text) for c in candidatos)
        if sim > mejor_sim:
            mejor_opt, mejor_sim = opt, sim

    if mejor_opt is not None and mejor_sim >= umbral:
        select.select_by_visible_text(mejor_opt.text)
        if mejor_sim < 0.95:
            log_func(f"{etiqueta} '{valor}' → '{mejor_opt.text}' (parecido {mejor_sim:.0%})")
        return True

    if mejor_opt is not None:
        log_func(f"⚠ {etiqueta} '{valor}': lo más parecido es '{mejor_opt.text}' "
                 f"({mejor_sim:.0%}), por debajo del mínimo exigido ({umbral:.0%}).")
    return False


def _esperar(driver, condicion, descripcion, timeout=10):
    """WebDriverWait que dice qué estaba esperando.

    Los TimeoutException de Selenium llegan con el mensaje vacío y un volcado de
    chromedriver, así que sin esto no hay forma de saber qué elemento faltó.
    """
    try:
        return WebDriverWait(driver, timeout).until(condicion)
    except TimeoutException:
        raise RuntimeError(f"se agotó la espera de {descripcion} ({timeout}s)")


def step_3_submit_report(driver, date_obj, project_name, partida, extracted_time, work_mode, log_func=print, observations="."):
    log_func(f"\n--- Salto 3: Generando reporte para {date_obj} ---")
    try:
        driver.get("https://jumpnasuvinsa.nasertic.es/Login.aspx")

        if len(driver.find_elements(By.ID, "MainContent_LoginUser_UserName")) > 0:
             config = load_config()
             driver.find_element(By.ID, "MainContent_LoginUser_UserName").send_keys(config.get("jump_user", ""))
             driver.find_element(By.ID, "Password").send_keys(config.get("jump_password", ""))
             driver.find_element(By.ID, "MainContent_LoginUser_Button1").click()

        partes_btn = _esperar(driver, EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'PARTES DE TRABAJO')]")),
                              "el menú 'PARTES DE TRABAJO'")
        driver.execute_script("arguments[0].click();", partes_btn)

        diario_btn = _esperar(driver, EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Parte de trabajo Diario')]")),
                              "el enlace 'Parte de trabajo Diario'")
        driver.execute_script("arguments[0].click();", diario_btn)

        # Fecha
        date_input = _esperar(driver, EC.presence_of_element_located((By.ID, "confec")),
                              "el campo de fecha del formulario")
        date_input.clear()
        date_input.send_keys(date_obj.strftime("%d/%m/%Y"))

        # Modo de trabajo (pexide dropdown)
        # Values: 1=Teletrabajo, 2=Presencial, 3=Presencial flexible
        try:
            mode_select = Select(_esperar(driver, EC.presence_of_element_located((By.ID, "pexide")),
                                          "el desplegable de modo de trabajo"))
            if "teletrabajo" in work_mode.lower():
                mode_select.select_by_value("1")
                log_func(f"Se ha detectado teletrabajo para el día {date_obj.strftime('%d/%m/%Y')}")
            else:  # Presencial
                mode_select.select_by_value("2")
        except Exception as e:
            log_func(f"Error selecting Work Mode: {e}")

        # Seleccionar proyecto
        project_select = Select(_esperar(driver, EC.presence_of_element_located((By.ID, "obride")),
                                         "el desplegable de proyecto"))
        if not _seleccionar_opcion(project_select, project_name, "Proyecto", log_func):
            log_func(f"Error: ningún proyecto se parece lo bastante a '{project_name}'. "
                     f"Se salta el día {date_obj.strftime('%d/%m/%Y')} sin imputar nada.")
            return False

        # Seleccionar partida: el desplegable se rellena por AJAX al elegir proyecto,
        # así que esperamos a que tenga opciones, no solo a que esté habilitado.
        _esperar(driver,
                 lambda d: d.find_element(By.ID, "fabproide").is_enabled()
                 and len(Select(d.find_element(By.ID, "fabproide")).options) > 1,
                 "que se carguen las partidas del proyecto", 25)
        time.sleep(1)
        partida_select = Select(driver.find_element(By.ID, "fabproide"))
        if not _seleccionar_opcion(partida_select, partida, "Partida", log_func):
            log_func(f"Error: no se ha encontrado la partida '{partida}' en el proyecto. "
                     f"Se salta el día {date_obj.strftime('%d/%m/%Y')} sin imputar nada.")
            return False

        # Horas
        h, m = map(int, extracted_time.split(':'))
        Select(driver.find_element(By.ID, "_hmores_can1")).select_by_value(f"{h:02d}")
        Select(driver.find_element(By.ID, "_hmores_can2")).select_by_value(f"{m:02d}")

        # Observaciones
        obs = driver.find_element(By.ID, "contex")
        obs.clear()
        obs.send_keys(observations if observations else ".")

        submit_btn = _esperar(driver, EC.presence_of_element_located((By.ID, "_btn4")),
                              "el botón de enviar el parte")
        driver.execute_script("arguments[0].click();", submit_btn)
        time.sleep(3)
        log_func("Parte metida.")
        return True

    except Exception as e:
        # Los errores de Selenium traen un volcado de chromedriver inservible:
        # nos quedamos con la primera línea, y si viene vacía, con el tipo.
        detalle = str(e).split("\n")[0].strip()
        if detalle in ("", "Message:"):
            detalle = type(e).__name__
        log_func(f"Error en Salto 3 ({date_obj.strftime('%d/%m/%Y')}): {detalle}")
        return False

def step_4_update_excel(df, partida, hours, minutes, log_func=print):
    log_func("\n--- Salto 4: Actualizando Excel ---")
    try:
        hours_decimal = hours + minutes / 60.0
        for col in ['Total Hours', 'Executed Hours', 'Available']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        df.loc[df['Partida'] == partida, 'Executed Hours'] += hours_decimal
        df['Available'] = df['Total Hours'] - df['Executed Hours']
        df['Executed Hours'] = df['Executed Hours'].round(2)
        df['Available'] = df['Available'].round(2)
        df.to_excel(PROJECTS_FILE, index=False)
        log_func("Excel actualizado.")
    except Exception as e:
        log_func(f"Error updating Excel: {e}")

def main(log_callback=None):
    def log(msg):
        print(msg)
        if log_callback: log_callback(msg)
        
    driver = setup_driver()
    
    try:
        last_date = step_0_get_last_reported_date(driver, log)
        if not last_date:
            log("No se pudo determinar la fecha del último reporte.")
            return
            
        missing_days = step_1_scrape_missing_days(driver, last_date, log)
        
        if not missing_days:
            log("No se han encontrado días para reportar.")
            return
            
        for day_data in missing_days:
            try:
                date_obj, time_str, mode = day_data
                
                proj_name, partida, h, m, df = step_2_find_project(time_str, date_obj, log)
                
                if proj_name:
                    success = step_3_submit_report(driver, date_obj, proj_name, partida, time_str, mode, log)
                    if success:
                        step_4_update_excel(df, partida, h, m, log)
                else:
                    log(f"Saltando {date_obj}: No se ha encontrado proyecto.")
            except Exception as e:
                log(f"Error procesando día {day_data}: {e}")
                log(traceback.format_exc())
                continue # Sigue al día siguiente
                
    except Exception as e:
        log(f"Fatal Error: {e}")
    finally:
        driver.quit()
        log("Hecho")

def _parse_bulk_hours(cantidad, cantidad2):
    """
    Cantidad  → formato hora de Excel (datetime.time, fracción float 0-1, o string HH:MM)
    Cantidad2 → horas decimales (7.5 = 7h 30min)
    Devuelve (h, m) como enteros.
    """
    h, m = 0, 0

    # Intentar Cantidad (formato hora)
    if pd.notna(cantidad) and str(cantidad).strip() not in ('', 'nan'):
        val = cantidad
        try:
            if hasattr(val, 'hour'):
                h, m = val.hour, val.minute
            elif isinstance(val, float) and 0.0 < val < 1.0:
                total_min = round(val * 24 * 60)
                h, m = divmod(total_min, 60)
            else:
                parts = str(val).strip().split(':')
                h = int(parts[0])
                m = int(parts[1]) if len(parts) > 1 else 0
        except:
            pass

    # Si Cantidad no dio resultado, usar Cantidad2 (decimal)
    if h == 0 and m == 0 and pd.notna(cantidad2) and str(cantidad2).strip() not in ('', 'nan'):
        try:
            dec = float(cantidad2)
            h = int(dec)
            m = round((dec - h) * 60)
        except:
            pass

    return h, m


def submit_bulk_from_excel(excel_path, log_callback=None):
    def log(msg):
        print(msg)
        if log_callback: log_callback(msg)

    try:
        df_bulk = pd.read_excel(excel_path)
    except Exception as e:
        log(f"Error al leer el Excel: {e}")
        return

    # Prefiltramos filas válidas para mostrar progreso real
    valid_rows = []
    for idx, row in df_bulk.iterrows():
        fecha_raw = row.get('Fecha', '')
        if not fecha_raw or str(fecha_raw).strip() in ('', 'nan'):
            continue
        proj = str(row.get('Proyecto', '')).strip()
        if not proj or proj.lower() == 'nan':
            continue
        h, m = _parse_bulk_hours(row.get('Cantidad'), row.get('Cantidad2'))
        if h == 0 and m == 0:
            log(f"Fila {idx+2}: horas 00:00 — saltando.")
            continue
        valid_rows.append((idx, row, h, m))

    total = len(valid_rows)
    log(f"Partes válidos a procesar: {total}")

    driver = setup_driver()
    try:
        for i, (idx, row, h, m) in enumerate(valid_rows):
            try:
                date_obj = pd.to_datetime(row.get('Fecha'), dayfirst=True).date()
                extracted_time = f"{h:02d}:{m:02d}"
                project_name = str(row.get('Proyecto', '')).strip()
                partida = str(row.get('Partida', '')).strip()
                work_mode = str(row.get('Modo de trabajo', 'Presencial')).strip()
                observations = str(row.get('Observaciones', '.')).strip()
                if not observations or observations.lower() == 'nan':
                    observations = '.'

                log(f"\n[{i+1}/{total}] {date_obj} | {project_name} | {partida} | {extracted_time} | {work_mode}")

                step_3_submit_report(driver, date_obj, project_name, partida, extracted_time, work_mode, log, observations)

            except Exception as e:
                log(f"Error procesando fila {idx+2}: {e}")
                log(traceback.format_exc())
                continue

    except Exception as e:
        log(f"Error fatal en carga masiva: {e}")
    finally:
        driver.quit()
        log("\n--- Carga masiva finalizada ---")


def _guardar_copia_borrados(driver, desde_fecha, hasta_fecha, log):
    """Extrae la tabla de resultados visible y la guarda como Excel en la carpeta Borrados/."""
    try:
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        borrados_dir = os.path.join(base_dir, "Borrados")
        os.makedirs(borrados_dir, exist_ok=True)

        table_data = driver.execute_script("""
            var img = document.querySelector('td.celda--Imagen img.Imagen--Tabla');
            if (!img) return null;
            var table = img.closest('table');
            if (!table) return null;
            var result = [];
            table.querySelectorAll('tr').forEach(function(row) {
                var cells = [];
                row.querySelectorAll('th, td').forEach(function(cell) {
                    cells.push(cell.innerText.trim());
                });
                result.push(cells);
            });
            return result;
        """)

        if not table_data:
            log("Aviso: no se pudieron extraer datos de la tabla para la copia de seguridad.")
            return

        headers = table_data[0] if table_data else []
        rows = table_data[1:] if len(table_data) > 1 else []

        # Limpiar cabeceras vacías/duplicadas
        seen = {}
        clean_headers = []
        for h in headers:
            key = h if h else "Col"
            if key in seen:
                seen[key] += 1
                key = f"{key}_{seen[key]}"
            else:
                seen[key] = 0
            clean_headers.append(key)

        df = pd.DataFrame(rows, columns=clean_headers)

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Borrados_{desde_fecha.strftime('%Y%m%d')}_{hasta_fecha.strftime('%Y%m%d')}_{ts}.xlsx"
        filepath = os.path.join(borrados_dir, filename)
        df.to_excel(filepath, index=False)
        log(f"Copia de seguridad guardada en: Borrados/{filename}")

    except Exception as e:
        log(f"Aviso: no se pudo guardar la copia de seguridad: {e}")


def delete_bulk_partes(desde_fecha, hasta_fecha, log_callback=None):
    """
    Borra todos los partes de trabajo en JUMP dentro del rango de fechas indicado.
    desde_fecha / hasta_fecha: objetos datetime.date
    """
    def log(msg):
        print(msg)
        if log_callback: log_callback(msg)

    if not desde_fecha or not hasta_fecha:
        log("Error: no se han especificado las fechas. Borrado cancelado.")
        return

    config = load_config()
    if not config:
        log("Error: no se encontró la configuración de credenciales.")
        return

    driver = setup_driver()
    try:
        log("Entrando en JUMP...")
        driver.get("https://jumpnasuvinsa.nasertic.es/Login.aspx")

        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "MainContent_LoginUser_UserName")))
        driver.find_element(By.ID, "MainContent_LoginUser_UserName").send_keys(config.get("jump_user", ""))
        driver.find_element(By.ID, "Password").send_keys(config.get("jump_password", ""))
        driver.find_element(By.ID, "MainContent_LoginUser_Button1").click()

        partes_btn = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'PARTES DE TRABAJO')]")))
        driver.execute_script("arguments[0].click();", partes_btn)
        time.sleep(2)

        consulta_btn = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Consulta de mis partes')]")))
        driver.execute_script("arguments[0].click();", consulta_btn)

        # Esperar a que cargue el formulario de búsqueda
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "MainContent_130")))
        time.sleep(1)

        # Rellenar fechas y disparar eventos para que ASP.NET las detecte
        desde_str = desde_fecha.strftime("%Y-%m-%d")
        hasta_str = hasta_fecha.strftime("%Y-%m-%d")
        driver.execute_script("""
            var d = document.getElementById('MainContent_130');
            var h = document.getElementById('MainContent_140');
            d.value = arguments[0];
            h.value = arguments[1];
            d.dispatchEvent(new Event('change', {bubbles:true}));
            h.dispatchEvent(new Event('change', {bubbles:true}));
        """, desde_str, hasta_str)

        log(f"Buscando partes entre {desde_fecha.strftime('%d/%m/%Y')} y {hasta_fecha.strftime('%d/%m/%Y')}...")

        # Click y esperar resultados
        url_antes = driver.current_url
        btn = driver.find_element(By.ID, "MainContent_Button1")
        driver.execute_script("arguments[0].scrollIntoView(true);", btn)
        time.sleep(0.5)
        btn.click()

        # Esperar máx 25s a que aparezcan filas o cambie la URL
        deadline = time.time() + 25
        sel_imgs = []
        while time.time() < deadline:
            time.sleep(1)
            sel_imgs = driver.find_elements(By.CSS_SELECTOR, "td.celda--Imagen img.Imagen--Tabla")
            if sel_imgs:
                break
            if driver.current_url != url_antes:
                time.sleep(2)
                sel_imgs = driver.find_elements(By.CSS_SELECTOR, "td.celda--Imagen img.Imagen--Tabla")
                break

        log(f"Filas encontradas: {len(sel_imgs)}")

        if not sel_imgs:
            log("No se han encontrado partes en ese rango de fechas.")
            return

        _guardar_copia_borrados(driver, desde_fecha, hasta_fecha, log)
        log(f"Encontrados {len(sel_imgs)} partes. Seleccionando...")
        for img in sel_imgs:
            try:
                driver.execute_script("arguments[0].click();", img)
                time.sleep(0.2)
            except Exception as e:
                log(f"Error seleccionando fila: {e}")

        # Clicar el botón de eliminar (papelera)
        trash_btn = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//img[contains(@src,'trash_can') or contains(@src,'Trash_can') or contains(@src,'TRASH_CAN')]"))
        )
        driver.execute_script("arguments[0].click();", trash_btn)
        log("Clic en botón eliminar...")

        # Confirmar el diálogo
        aceptar_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "aceptarPregunta")))
        driver.execute_script("arguments[0].click();", aceptar_btn)
        time.sleep(3)
        log("Partes eliminados correctamente.")

    except Exception as e:
        log(f"Error en borrado masivo: {e}")
        log(traceback.format_exc())
    finally:
        driver.quit()
        log("--- Borrado masivo finalizado ---")


if __name__ == "__main__":
    main()
