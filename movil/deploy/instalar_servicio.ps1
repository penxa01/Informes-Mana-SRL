<#
Instala la API movil como tarea programada de Windows: arranca sola al encender
el equipo (aunque nadie inicie sesion), corre como SYSTEM y se reinicia sola si
se cae. Se corre UNA vez, en el servidor, como administrador y desde la ruta
LOCAL del servidor (no desde una unidad de red como Z:).

  powershell -ExecutionPolicy Bypass -File .\instalar_servicio.ps1
      -ConfigurarTailscale   ademas la expone por HTTPS con "tailscale serve"
      -SoloVerificar         solo revisa los requisitos, no instala nada
      -Python C:\ruta\python.exe   si no detecta el Python correcto

Volver a correrlo es seguro: reemplaza la tarea anterior.
(Este archivo es ASCII a proposito: PowerShell 5.1 lee mal los acentos sin BOM.)
#>
param(
    [string]$Python = "",
    [string]$Nombre = "ManaPedidosMovil",
    [switch]$ConfigurarTailscale,
    [switch]$SoloVerificar
)

$ErrorActionPreference = "Stop"

function Fallar($mensaje) { Write-Host "ERROR: $mensaje" -ForegroundColor Red; exit 1 }
function Paso($mensaje)   { Write-Host "[..] $mensaje" -ForegroundColor Cyan }
function Listo($mensaje)  { Write-Host "[ok] $mensaje" -ForegroundColor Green }

$raiz = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$movil = Join-Path $raiz "movil"
$lanzador = Join-Path $movil "run.py"
$envFile = Join-Path $movil ".env"

Paso "Carpeta del sistema: $raiz"

# 1. Administrador
if (-not $SoloVerificar) {
    $identidad = [Security.Principal.WindowsIdentity]::GetCurrent()
    $esAdmin = ([Security.Principal.WindowsPrincipal]$identidad).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $esAdmin) {
        Fallar "Hay que correrlo como administrador (clic derecho en PowerShell > Ejecutar como administrador)."
    }
}

# 2. Ruta local: una tarea de Windows (SYSTEM) no ve las unidades de red ni las letras mapeadas
if ($raiz.StartsWith("\\")) {
    Fallar "La carpeta esta en una ruta de red ($raiz). Corre el script desde la ruta LOCAL del servidor."
}
$unidad = Split-Path -Qualifier $raiz
$disco = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$unidad'"
if ($disco -and $disco.DriveType -eq 4) {
    Fallar "La carpeta esta en la unidad de red $unidad. Una tarea de Windows no ve las unidades de red: corre el script desde la ruta LOCAL del servidor (la carpeta que se comparte como Z:)."
}

# 3. Archivos
if (-not (Test-Path $lanzador)) { Fallar "No encuentro $lanzador" }
if (-not (Test-Path $envFile)) {
    Fallar "Falta $envFile . Copialo desde la PC donde se probo (tiene la clave de la base) o armalo desde movil\env.example."
}

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

# 5. Librerias (se prueba con ese mismo Python)
$anterior = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Python -c "import fastapi, uvicorn, psycopg2, bcrypt, pydantic" *> $null
$codigoLibrerias = $LASTEXITCODE
$ErrorActionPreference = $anterior
if ($codigoLibrerias -ne 0) {
    Fallar "Faltan librerias en ese Python. Instalalas con:  `"$Python`" -m pip install -r `"$movil\requirements.txt`""
}
Listo "Librerias instaladas"

# Puerto (MOVIL_PORT del .env, por defecto 8000)
$puerto = 8000
$lineaPuerto = Get-Content $envFile | Where-Object { $_ -match '^\s*MOVIL_PORT\s*=' } | Select-Object -First 1
if ($lineaPuerto -and ($lineaPuerto -match '(\d+)\s*$')) { $puerto = [int]$Matches[1] }

if ($SoloVerificar) {
    Listo "Requisitos OK (modo -SoloVerificar: no se instalo nada). Puerto que usaria: $puerto"
    exit 0
}

# 6. Proteger el .env: tiene la clave de la base y el secreto de los tokens, y esta carpeta se
#    comparte con la red de la oficina. Queda legible solo para Administradores y SYSTEM
#    (por SID: el nombre "Administradores" cambia segun el idioma de Windows).
Paso "Restringiendo los permisos de $envFile ..."
icacls $envFile /inheritance:r /grant:r "*S-1-5-18:(R)" "*S-1-5-32-544:(F)" | Out-Null
if ($LASTEXITCODE -ne 0) { Fallar "No pude restringir los permisos de $envFile" }
Listo ".env legible solo por Administradores y SYSTEM"

# 7. Registrar la tarea
Paso "Registrando la tarea programada '$Nombre'..."
if (Get-ScheduledTask -TaskName $Nombre -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $Nombre -ErrorAction SilentlyContinue
}
$accion = New-ScheduledTaskAction -Execute $Python -Argument ('"{0}"' -f $lanzador) -WorkingDirectory $raiz
$disparador = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
# Sin limite de tiempo (el default de Windows la mataria a los 3 dias) y con reintento cada minuto si se cae.
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
Register-ScheduledTask -TaskName $Nombre -Action $accion -Trigger $disparador -Principal $principal `
    -Settings $ajustes -Description "API movil de pedidos (Mana). Ver movil\README.md" -Force | Out-Null
Listo "Tarea registrada (arranca sola al encender el equipo)"

# 8. Arrancarla ahora y comprobar que responde
Paso "Arrancando la API..."
Start-ScheduledTask -TaskName $Nombre
$url = "http://127.0.0.1:$puerto/health"
$respuesta = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try { $respuesta = Invoke-RestMethod -Uri $url -TimeoutSec 2; break } catch { }
}
if (-not $respuesta) {
    Fallar "La tarea se registro pero la API no responde en $url . Mira el log: $movil\logs\api.log"
}
Listo "La API responde en $url  (api=$($respuesta.api), db=$($respuesta.db))"
if ($respuesta.db -ne "ok") {
    Write-Host "AVISO: la API corre pero no llega a la base ($($respuesta.db)). Revisa las PEDIDOS_DB_* de $envFile" -ForegroundColor Yellow
}

# 9. HTTPS por Tailscale
$comandoTailscale = "tailscale serve --bg http://127.0.0.1:$puerto"
if ($ConfigurarTailscale) {
    if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) {
        Write-Host "AVISO: no encuentro 'tailscale' en el PATH. Correlo a mano: $comandoTailscale" -ForegroundColor Yellow
    } else {
        & tailscale serve --bg "http://127.0.0.1:$puerto"
        Listo "Expuesta por HTTPS con Tailscale"
    }
} else {
    Write-Host ""
    Write-Host "Falta exponerla por HTTPS (una sola vez, en esta PC):  $comandoTailscale"
}

Write-Host ""
Write-Host "Listo. Para probar que sube sola: reinicia el equipo y abri http://127.0.0.1:$puerto/health"
Write-Host "Log:       $movil\logs\api.log"
Write-Host "Reiniciar: Stop-ScheduledTask -TaskName $Nombre; Start-ScheduledTask -TaskName $Nombre"
Write-Host "Quitar:    .\desinstalar_servicio.ps1"
