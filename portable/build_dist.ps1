# build_dist.ps1 - Prepara la carpeta que se reparte, a partir de la instalacion de trabajo.
# Copia SapoPartero -> SapoPartero_dist excluyendo datos personales:
#   config.json, projects.xlsx, la carpeta neria y las caches __pycache__.
# Uso:  powershell -ExecutionPolicy Bypass -File build_dist.ps1 [-Zip]
#       (o boton derecho sobre el fichero -> Ejecutar con PowerShell)

param([switch]$Zip)

$ErrorActionPreference = 'Stop'

$portableDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Join-Path $portableDir 'SapoPartero'
$dst = Join-Path $portableDir 'SapoPartero_dist'

if (-not (Test-Path $src)) { throw "No existe la carpeta de origen: $src" }

# --- 1. Copia limpia (robocopy devuelve <8 en exito) ---
if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
robocopy $src $dst /E /XD 'neria' '__pycache__' 'Borrados' 'version_anterior_*' /XF 'config.json' 'projects.xlsx' /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy fallo (exit $LASTEXITCODE)" }

# --- 2. Smoke test de imports con el Python empaquetado ---
& (Join-Path $dst 'python\python.exe') -c "import tkinter, selenium, pandas, openpyxl, ttkthemes, PIL; print('imports OK')"
if ($LASTEXITCODE -ne 0) { throw 'Smoke test de imports fallo' }

# --- 3. Limpiar la cache de bytecode que acaba de generar el smoke test ---
Get-ChildItem $dst -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force

# --- 4. Verificar, ya al final, que no se ha colado nada personal ni cache ---
$fugas = @()
$fugas += Get-ChildItem $dst -Recurse -Filter 'config*.json'   -ErrorAction SilentlyContinue
$fugas += Get-ChildItem $dst -Recurse -Filter 'projects*.xlsx' -ErrorAction SilentlyContinue
$fugas += Get-ChildItem $dst -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue
if ($fugas.Count -gt 0) {
    $fugas | ForEach-Object { Write-Host "  FUGA: $($_.FullName)" -ForegroundColor Red }
    throw 'Se han colado ficheros personales en el paquete. Revisa las exclusiones.'
}

$mb = [math]::Round((Get-ChildItem $dst -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
Write-Host "Paquete limpio listo: $dst  ($mb MB)" -ForegroundColor Green

# --- 5. Zip opcional (si no, comprime la carpeta con PeaZip en formato ZIP) ---
if ($Zip) {
    $zipOut = Join-Path $portableDir 'SapoPartero_dist.zip'
    if (Test-Path $zipOut) { Remove-Item $zipOut }
    Write-Host 'Comprimiendo... (puede tardar un par de minutos)'
    Compress-Archive -Path $dst -DestinationPath $zipOut
    Write-Host "Zip creado: $zipOut" -ForegroundColor Green
}
