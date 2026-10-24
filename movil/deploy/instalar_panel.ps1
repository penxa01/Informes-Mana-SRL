<#
Instala el proceso que arma el PANEL DE CONTROL como tarea programada de Windows: arranca
solo al encender el equipo, corre como SYSTEM y se reinicia si se cae. Lee los archivos del
sistema de gestion (DBF en D:\tiempo del servidor) y deja el resultado en la base, de donde
lo toma la API. Se corre UNA vez, en el servidor, como administrador y desde la ruta LOCAL
del servidor (no desde una unidad de red como Z:). Requiere que ya este instalada la API
(instalar_servicio.ps1: usa el mismo movil\.env).

  powershell -ExecutionPolicy Bypass -File .\instalar_panel.ps1
      -SoloVerificar         solo revisa los requisitos, no instala nada
      -Python C:\ruta\python.exe   si no detecta el Python correcto

Volver a correrlo es seguro: reemplaza la tarea anterior.
Para quitarlo:  .\desinstalar_servicio.ps1 -Nombre ManaPanelMovil
(Este archivo es ASCII a proposito: PowerShell 5.1 lee mal los acentos sin BOM.)
#>
param(
    [string]$Python = "",
    [string]$Nombre = "ManaPanelMovil",
    [switch]$SoloVerificar
)

$ErrorActionPreference = "Stop"

function Fallar($mensaje) { Write-Host "ERROR: $mensaje" -ForegroundColor Red; exit 1 }
function Paso($mensaje)   { Write-Host "[..] $mensaje" -ForegroundColor Cyan }
function Listo($mensaje)  { Write-Host "[ok] $mensaje" -ForegroundColor Green }

$raiz = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$movil = Join-Path $raiz "movil"
$envFile = Join-Path $movil ".env"
$logPanel = Join-Path $movil "logs\panel.log"

Paso "Carpeta del sistema: $raiz"

# 1. Administrador
if (-not $SoloVerificar) {
    $identidad = [Security.Principal.WindowsIdentity]::GetCurrent()
    $esAdmin = ([Security.Principal.WindowsPrincipal]$identidad).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $esAdmin) {
        Fallar "Hay que correrlo como administrador (clic derecho en PowerShell > Ejecutar como administrador)."
    }
}

# 2. Ruta local (una tarea de Windows no ve las unidades de red)
if ($raiz.StartsWith("\\")) {
    Fallar "La carpeta esta en una ruta de red ($raiz). Corre el script desde la ruta LOCAL del servidor."
}
$unidad = Split-Path -Qualifier $raiz
$disco = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$unidad'"
if ($disco -and $disco.DriveType -eq 4) {
    Fallar "La carpeta esta en la unidad de red $unidad. Corre el script desde la ruta LOCAL del servidor (la carpeta que se comparte como Z:)."
}

# 3. .env
if (-not (Test-Path $envFile)) { Fallar "Falta $envFile (el mismo que usa la API)." }

# 4. Python
if (-not $Python) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $Python = $cmd.Source }
}
if (-not $Python -or -not (Test-Path $Python)) {
    Fallar "No encuentro Python. Indicalo con -Python C:\ruta\python.exe"
}
if ($Python -like "*\WindowsApps\*") {
    Fallar "Ese 'python' es el acceso directo de la Microsoft Store y SYSTEM no puede usarlo. Indica el Python real con -Python."
}
Listo "Python: $Python"

# 5. Librerias (se prueban con ese mismo Python)
$anterior = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Python -c "import pandas, dbfread, openpyxl, psycopg2" *> $null
$codigoLibrerias = $LASTEXITCODE
$ErrorActionPreference = $anterior
if ($codigoLibrerias -ne 0) {
    Fallar "Faltan librerias en ese Python. Instalalas con:  `"$Python`" -m pip install -r `"$movil\requirements-panel.txt`""
}
Listo "Librerias instaladas (pandas, dbfread, openpyxl)"

# 6. Archivos del sistema de gestion (PANEL_BASE_PATH del .env, por defecto D:/tiempo)
$base = "D:/tiempo"
$lineaBase = Get-Content $envFile | Where-Object { $_ -match '^\s*PANEL_BASE_PATH\s*=' } | Select-Object -First 1
if ($lineaBase) { $base = ($lineaBase -replace '^\s*PANEL_BASE_PATH\s*=\s*', '').Trim().Trim('"').Trim("'") }
$dbf = Join-Path $base "vtiempoges\GESTION\MANA2014"
$archivos = @(
    (Join-Path $dbf "fachist.DBF"),
    (Join-Path $dbf "abmartic.DBF"),
    (Join-Path $dbf "ctacorr.DBF"),
    (Join-Path $base "Thalamus\LITROS SHELL.xlsx")
)
foreach ($a in $archivos) {
    if (-not (Test-Path $a)) {
        Fallar "No encuentro $a . Si el sistema de gestion esta en otra carpeta, agrega PANEL_BASE_PATH=<carpeta> al .env."
    }
}
Listo "Archivos del sistema encontrados en $base"

if ($SoloVerificar) {
    Listo "Requisitos OK (modo -SoloVerificar: no se instalo nada)."
    exit 0
}

# 7. Registrar la tarea
Paso "Registrando la tarea programada '$Nombre'..."
if (Get-ScheduledTask -TaskName $Nombre -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $Nombre -ErrorAction SilentlyContinue
}
# Se corre como modulo desde la carpeta del sistema (WorkingDirectory) para que encuentre el paquete movil.
$accion = New-ScheduledTaskAction -Execute $Python -Argument "-m movil.panel.worker" -WorkingDirectory $raiz
$disparador = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
Register-ScheduledTask -TaskName $Nombre -Action $accion -Trigger $disparador -Principal $principal `
    -Settings $ajustes -Description "Calculo del panel de control movil (Mana). Ver movil\README.md" -Force | Out-Null
Listo "Tarea registrada (arranca sola al encender el equipo)"

# 8. Arrancarla y esperar el primer calculo (leer los archivos grandes lleva de 15 a 60 segundos)
Paso "Arrancando el calculo (el primero puede tardar un minuto)..."
$inicio = Get-Date
Start-ScheduledTask -TaskName $Nombre
$resultado = $null
for ($i = 0; $i -lt 180; $i++) {
    Start-Sleep -Seconds 2
    if (Test-Path $logPanel) {
        $nuevas = Get-Content $logPanel -Encoding UTF8 | Select-Object -Last 40
        if ($nuevas -match "Ciclo: calculado") { $resultado = "calculado"; break }
        if ($nuevas -match "No se pudo calcular el panel|El ciclo fall") { $resultado = "error"; break }
    }
}
if ($resultado -eq "calculado") {
    Listo "Primer calculo del panel hecho. La API ya puede mostrarlo."
} elseif ($resultado -eq "error") {
    Write-Host "AVISO: el primer calculo fallo. Mira el final de: $logPanel" -ForegroundColor Yellow
} else {
    Write-Host "AVISO: no vi terminar el primer calculo todavia. Mira: $logPanel" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Log:       $logPanel"
Write-Host "Reiniciar: Stop-ScheduledTask -TaskName $Nombre; Start-ScheduledTask -TaskName $Nombre"
Write-Host "Quitar:    .\desinstalar_servicio.ps1 -Nombre $Nombre"
