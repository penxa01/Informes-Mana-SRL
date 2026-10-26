<#
Frena y borra la tarea programada de la API movil (no toca los archivos ni la base).
Se corre como administrador:  powershell -ExecutionPolicy Bypass -File .\desinstalar_servicio.ps1
(ASCII a proposito: PowerShell 5.1 lee mal los acentos sin BOM.)
#>
param([string]$Nombre = "ManaPedidosMovil")

$ErrorActionPreference = "Stop"

$identidad = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]$identidad).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "ERROR: hay que correrlo como administrador." -ForegroundColor Red
    exit 1
}

if (-not (Get-ScheduledTask -TaskName $Nombre -ErrorAction SilentlyContinue)) {
    Write-Host "La tarea '$Nombre' no existe: no hay nada que quitar."
    exit 0
}

Stop-ScheduledTask -TaskName $Nombre -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $Nombre -Confirm:$false
Write-Host "[ok] Tarea '$Nombre' eliminada. La API ya no arranca sola ni esta corriendo." -ForegroundColor Green
Write-Host "Si la expusiste con Tailscale y queres sacarla:  tailscale serve reset"
