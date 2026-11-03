<#
Instala el proceso que manda los AVISOS (notificaciones push) a los celulares como tarea programada de
Windows: arranca solo al encender el equipo, corre como SYSTEM y se reinicia si se cae. Mira la tabla de
pedidos cada pocos segundos y avisa de un pedido nuevo de un vendedor, un pedido programado y un pedido
entregado. Se corre UNA vez, en el servidor, como administrador y desde la ruta LOCAL del servidor (no
desde una unidad de red como Z:). Requiere que ya esten: la API (instalar_servicio.ps1: usa el mismo
movil\.env), la migracion 004 aplicada en la base y las claves VAPID en el .env
(python movil\vapid.py --contacto mailto:...).

  powershell -ExecutionPolicy Bypass -File .\instalar_avisos.ps1
      -SoloVerificar         solo revisa los requisitos, no instala nada
      -Python C:\ruta\python.exe   si no detecta el Python correcto

Volver a correrlo es seguro: reemplaza la tarea anterior.
Para quitarlo:  .\desinstalar_servicio.ps1 -Nombre ManaAvisosMovil
(Este archivo es ASCII a proposito: PowerShell 5.1 lee mal los acentos sin BOM.)
#>
param(
    [string]$Python = "",
    [string]$Nombre = "ManaAvisosMovil",
    [switch]$SoloVerificar
)

$ErrorActionPreference = "Stop"

function Fallar($mensaje) { Write-Host "ERROR: $mensaje" -ForegroundColor Red; exit 1 }
function Paso($mensaje)   { Write-Host "[..] $mensaje" -ForegroundColor Cyan }
function Listo($mensaje)  { Write-Host "[ok] $mensaje" -ForegroundColor Green }

$raiz = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$movil = Join-Path $raiz "movil"
$envFile = Join-Path $movil ".env"
$logAvisos = Join-Path $movil "logs\avisos.log"

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

# 3. .env con las claves de los avisos (se miran los nombres, nunca se muestran los valores)
if (-not (Test-Path $envFile)) { Fallar "Falta $envFile (el mismo que usa la API)." }
foreach ($variable in @("MOVIL_VAPID_PRIVADA", "MOVIL_VAPID_CONTACTO")) {
    $linea = Get-Content $envFile | Where-Object { $_ -match "^\s*$variable\s*=\s*\S" } | Select-Object -First 1
    if (-not $linea) {
        Fallar "Falta $variable en el .env. Se generan UNA vez con:  python movil\vapid.py --contacto mailto:CORREO"
    }
}
Listo "El .env tiene las claves de los avisos"

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

# 5. Librerias (se prueban con ese mismo Python). pywebpush usa cryptography, que trae una parte en Rust: si
# falla con "DLL load failed" suele faltar el "Visual C++ Redistributable" de Microsoft (x64).
$anterior = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$salida = & $Python -c "import psycopg2; from pywebpush import webpush" 2>&1
$codigoLibrerias = $LASTEXITCODE
$ErrorActionPreference = $anterior
if ($codigoLibrerias -ne 0) {
    Write-Host ($salida | Select-Object -Last 3 | Out-String) -ForegroundColor DarkGray
    Fallar "Faltan librerias o no cargan en ese Python. Instalalas con:  `"$Python`" -m pip install -r `"$movil\requirements-avisos.txt`"  (si dice DLL load failed: instalar el Visual C++ Redistributable x64 y reintentar)"
}
Listo "Librerias instaladas y cargan (psycopg2, pywebpush)"

if ($SoloVerificar) {
    Listo "Requisitos OK (modo -SoloVerificar: no se instalo nada)."
    exit 0
}

# 6. Registrar la tarea
Paso "Registrando la tarea programada '$Nombre'..."
if (Get-ScheduledTask -TaskName $Nombre -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $Nombre -ErrorAction SilentlyContinue
}
# Se corre como modulo desde la carpeta del sistema (WorkingDirectory) para que encuentre el paquete movil.
$accion = New-ScheduledTaskAction -Execute $Python -Argument "-m movil.avisos.worker" -WorkingDirectory $raiz
$disparador = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
Register-ScheduledTask -TaskName $Nombre -Action $accion -Trigger $disparador -Principal $principal `
    -Settings $ajustes -Description "Avisos (notificaciones push) del sistema movil de Mana. Ver movil\README.md" -Force | Out-Null
Listo "Tarea registrada (arranca sola al encender el equipo)"

# 7. Arrancarla y esperar a que diga que esta lista (la primera vez siembra lo que ya existe)
Paso "Arrancando los avisos..."
Start-ScheduledTask -TaskName $Nombre
$resultado = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    if (Test-Path $logAvisos) {
        $nuevas = Get-Content $logAvisos -Encoding UTF8 | Select-Object -Last 40
        if ($nuevas -match "Avisos listos") { $resultado = "listo"; break }
        if ($nuevas -match "CRITICAL|El ciclo fall") { $resultado = "error"; break }
    }
}
if ($resultado -eq "listo") {
    Listo "Avisos funcionando."
} elseif ($resultado -eq "error") {
    Write-Host "AVISO: el proceso no pudo arrancar. Mira el final de: $logAvisos" -ForegroundColor Yellow
} else {
    Write-Host "AVISO: no vi que terminara de arrancar todavia. Mira: $logAvisos" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Log:       $logAvisos"
Write-Host "Reiniciar: Stop-ScheduledTask -TaskName $Nombre; Start-ScheduledTask -TaskName $Nombre"
Write-Host "Quitar:    .\desinstalar_servicio.ps1 -Nombre $Nombre"
