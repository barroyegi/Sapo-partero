# build_portable.ps1 - Empaqueta Sapo Partero como aplicacion portatil (sin Python instalado, sin exe PyInstaller).
# Uso:  powershell -ExecutionPolicy Bypass -File build_portable.ps1 [-Zip]
# Requiere: Python 3.13 instalado en la maquina de empaquetado (mismo minor que el embeddable).

param([switch]$Zip)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$portableDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projDir     = Split-Path -Parent $portableDir
$pkg         = Join-Path $portableDir 'SapoPartero'
$pyVer       = '3.13.5'
$embedZip    = Join-Path $portableDir "python-$pyVer-embed-amd64.zip"

# --- 1. Descargar Python embeddable (se cachea el zip) ---
if (-not (Test-Path $embedZip)) {
    Write-Host "Descargando Python $pyVer embeddable..."
    Invoke-WebRequest "https://www.python.org/ftp/python/$pyVer/python-$pyVer-embed-amd64.zip" -OutFile $embedZip
}

# --- 2. Carpeta de paquete limpia ---
if (Test-Path $pkg) { Remove-Item -Recurse -Force $pkg }
New-Item -ItemType Directory -Force "$pkg\python" | Out-Null
Expand-Archive $embedZip -DestinationPath "$pkg\python"

# --- 3. Habilitar Lib y site-packages en el ._pth ---
$pth = Get-ChildItem "$pkg\python" -Filter 'python*._pth' | Select-Object -First 1
@(
    'python313.zip'
    '.'
    '..'
    'Lib'
    'Lib\site-packages'
    'import site'
) | Set-Content -Encoding Ascii $pth.FullName

# --- 4. Dependencias (instaladas con el Python local, mismo 3.13) ---
$sitePkg = Join-Path $pkg 'python\Lib\site-packages'
New-Item -ItemType Directory -Force $sitePkg | Out-Null
# Versiones fijadas = las del entorno de desarrollo verificado
python -m pip install --target $sitePkg --no-warn-script-location `
    selenium==4.39.0 pandas==2.3.3 numpy==2.3.5 openpyxl==3.1.5 ttkthemes==3.3.0 Pillow==12.0.0
if ($LASTEXITCODE -ne 0) { throw "pip install fallo (exit $LASTEXITCODE)" }

# --- 5. tkinter (el embeddable no lo trae): copiar de la instalacion local ---
$pyHome = Split-Path (Get-Command python).Source
Copy-Item "$pyHome\tcl" (Join-Path $pkg 'python\tcl') -Recurse
Copy-Item "$pyHome\Lib\tkinter" (Join-Path $pkg 'python\Lib\tkinter') -Recurse
Copy-Item "$pyHome\DLLs\_tkinter.pyd", "$pyHome\DLLs\tcl86t.dll", "$pyHome\DLLs\tk86t.dll", "$pyHome\DLLs\zlib1.dll" (Join-Path $pkg 'python')

# --- 6. Ficheros de la aplicacion (config.json y projects.xlsx NO: los crea la app) ---
'gui_app.py', 'automation_script.py', 'updater.py', 'plantilla_partes.xlsx', 'sapo_partero.ico', 'sapo_partero.png' |
    ForEach-Object { Copy-Item (Join-Path $projDir $_) $pkg }

# --- 7. INSTALAR.bat: crea acceso directo con icono en el escritorio y lanza la app ---
$instalar = @'
@echo off
set "APPDIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Sapo Partero.lnk');" ^
 "$s.TargetPath='%APPDIR%python\pythonw.exe';" ^
 "$s.Arguments='\"%APPDIR%gui_app.py\"';" ^
 "$s.WorkingDirectory='%APPDIR%';" ^
 "$s.IconLocation='%APPDIR%sapo_partero.ico';" ^
 "$s.Save()"
echo Acceso directo "Sapo Partero" creado en el escritorio.
start "" "%APPDIR%python\pythonw.exe" "%APPDIR%gui_app.py"
'@
Set-Content -Path (Join-Path $pkg 'INSTALAR.bat') -Value $instalar -Encoding Ascii

# --- 8. LEEME.txt ---
$leeme = @'
SAPO PARTERO - version portatil
===============================

Instalacion:
  1. Descomprime esta carpeta donde quieras (p. ej. C:\SapoPartero).
     Importante: NO la muevas despues de instalar (el acceso directo
     guarda la ruta). Si la mueves, vuelve a ejecutar INSTALAR.bat.
  2. Doble clic en INSTALAR.bat (solo la primera vez).
     - Crea el acceso directo "Sapo Partero" en el escritorio.
     - Abre la aplicacion.
  3. A partir de ahi, usa el acceso directo del escritorio.

Requisitos:
  - Google Chrome instalado.
  - Conexion a internet la primera vez (Selenium descarga su
    chromedriver automaticamente).

No requiere instalar Python ni permisos de administrador.
'@
Set-Content -Path (Join-Path $pkg 'LEEME.txt') -Value $leeme -Encoding UTF8

# --- 9. Smoke test de imports con el Python empaquetado ---
& (Join-Path $pkg 'python\python.exe') -c "import tkinter, selenium, pandas, openpyxl, ttkthemes, PIL; print('imports OK')"
if ($LASTEXITCODE -ne 0) { throw 'Smoke test de imports fallo' }

# --- 10. Limpiar cache de bytecode generada por los tests ---
Get-ChildItem $pkg -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force

# --- 11. Zip opcional para distribuir ---
if ($Zip) {
    $zipOut = Join-Path $portableDir 'SapoPartero.zip'
    if (Test-Path $zipOut) { Remove-Item $zipOut }
    Compress-Archive -Path $pkg -DestinationPath $zipOut
    Write-Host "Zip creado: $zipOut"
}

Write-Host "Paquete listo en: $pkg"
