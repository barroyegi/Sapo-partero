<p align="center">
  <img src="sapo_partero.png" alt="Sapo Partero" width="140">
</p>

<h1 align="center">Sapo Partero</h1>

<p align="center">
  Automatización de partes de trabajo: lee las horas fichadas en Kelio y las imputa en JUMP.
</p>

---

## Qué hace

La aplicación consulta las horas registradas en Kelio, detecta los días que
todavía no se han imputado en JUMP y crea los partes correspondientes,
repartiéndolos entre los proyectos que se hayan configurado.

Tiene en cuenta varias particularidades del trabajo diario:

- Distingue los días de teletrabajo de los presenciales y los marca en consecuencia.
- Omite los fines de semana y los días sin fichajes, que se interpretan como vacaciones o ausencias.
- Reparte las horas entre los proyectos disponibles dando más peso a los que tienen
  más horas asignadas y a los que están más cerca de su fecha límite.
- Lleva la cuenta de las horas consumidas en un Excel, de modo que ningún proyecto
  supere las horas que tiene presupuestadas.

Además de la automatización diaria, admite la carga masiva de partes desde una
plantilla de Excel y el borrado de todos los partes de un rango de fechas.

## Requisitos

- Windows 10 o superior.
- Google Chrome instalado.
- Conexión a internet la primera vez, para que Selenium descargue su controlador.

No hace falta instalar Python ni disponer de permisos de administrador: el paquete
portátil incluye su propio intérprete.

## Instalación

1. Descargar el archivo `SapoPartero_dist.zip` de la sección
   [Releases](../../releases).
2. Descomprimirlo en una carpeta estable, por ejemplo `C:\SapoPartero`.
   Conviene no moverla después, porque el acceso directo guarda la ruta.
3. Ejecutar `INSTALAR.bat` una sola vez. Crea el acceso directo en el escritorio
   y abre la aplicación.
4. A partir de ese momento, se utiliza el acceso directo.

Si Windows muestra un aviso de SmartScreen al abrir el archivo descargado, se
resuelve desbloqueando el ZIP antes de descomprimirlo: botón derecho sobre el
archivo, Propiedades, y marcar la casilla Desbloquear.

## Primeros pasos

La aplicación guía el proceso en tres pantallas.

**1. Credenciales.** Usuario y contraseña de Kelio y de JUMP. Son independientes
entre sí y se guardan en un archivo `config.json` junto a la aplicación, en el
equipo de cada usuario.

**2. Proceso.** Se elige qué se quiere hacer:

| Proceso | Descripción |
|---|---|
| Automatización normal | Lee Kelio y crea en JUMP los partes que falten. |
| Carga masiva desde Excel | Envía los partes definidos en una plantilla. |
| Borrado masivo | Elimina todos los partes de un rango de fechas. |

Para la automatización normal hay que configurar antes al menos un proyecto,
desde el botón Gestión de Proyectos. De cada uno se indica el nombre, la partida,
las horas totales disponibles y, opcionalmente, una fecha límite.

**3. Ejecución.** Muestra el registro de actividad en tiempo real. Desde esta
pantalla también puede programarse una tarea diaria que ejecute el proceso
automáticamente a las nueve de la mañana.

## Carga masiva

La plantilla `plantilla_partes.xlsx` se copia junto a la aplicación la primera vez
que se abre. Las columnas que utiliza son las siguientes:

| Columna | Contenido |
|---|---|
| Fecha | Día del parte. |
| Proyecto | Nombre del proyecto en JUMP. |
| Partida | Código de la partida. |
| Cantidad | Horas en formato HH:MM. |
| Cantidad2 | Alternativa a la anterior, en horas decimales (7,5 equivale a siete horas y media). |
| Modo de trabajo | Presencial o Teletrabajo. |
| Observaciones | Texto libre. Opcional. |

Antes de enviar nada, la aplicación muestra la lista completa de partes para su
revisión.

## Borrado masivo

Elimina todos los partes comprendidos entre dos fechas. Antes de borrar, guarda
una copia de los datos en la carpeta `Borrados`, en un archivo de Excel con la
fecha y la hora de la operación. La acción no puede deshacerse desde la
aplicación, de modo que conviene revisar el rango antes de confirmarlo.

## Actualizaciones

Al abrirse, la aplicación comprueba en segundo plano si hay una versión más
reciente publicada en este repositorio. Si la encuentra, muestra la lista de
cambios y ofrece instalarla; la decisión es siempre del usuario. También puede
comprobarse manualmente desde la primera pantalla.

La actualización sustituye únicamente los archivos de código, que ocupan menos de
cien kilobytes. El intérprete de Python no se descarga de nuevo. Antes de
instalar nada se verifica que lo descargado es válido, y se conserva una copia de
la versión anterior por si fuera necesario volver atrás. Los archivos de
configuración y el Excel de proyectos no se tocan en ningún momento.

## Desarrollo

El repositorio contiene el código fuente. Para generar el paquete portátil hace
falta tener Python 3.13 instalado.

```powershell
# Genera el paquete completo, con intérprete y dependencias
powershell -ExecutionPolicy Bypass -File portable\build_portable.ps1

# Prepara la copia que se distribuye, sin credenciales ni datos personales
powershell -ExecutionPolicy Bypass -File portable\build_dist.ps1 -Zip
```

Para publicar una versión nueva hay que actualizar el número de versión en
`updater.py` y reflejar el mismo número, junto con la lista de cambios, en
`version.json`.

Conviene tener presente que ni las credenciales ni los datos de horas deben
llegar al repositorio. El archivo `.gitignore` los excluye, pero merece la pena
revisar `git status` antes de cada commit.

## Estructura

| Archivo | Cometido |
|---|---|
| `gui_app.py` | Interfaz gráfica y asistente de tres pasos. |
| `automation_script.py` | Automatización de Kelio y JUMP con Selenium. |
| `updater.py` | Comprobación e instalación de actualizaciones. |
| `version.json` | Versión publicada y lista de cambios. |
| `portable/build_portable.ps1` | Construcción del paquete portátil. |
| `portable/build_dist.ps1` | Preparación de la copia distribuible. |

## Autor

Beñat Arroyo
