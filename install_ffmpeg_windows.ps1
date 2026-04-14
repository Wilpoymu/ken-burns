# ══════════════════════════════════════════════════════════════════════════════
#  install_ffmpeg_windows.ps1
#  Descarga e instala FFmpeg en Windows y lo agrega al PATH del usuario
#  
#  EJECUCIÓN (como usuario normal, NO requiere Administrador):
#    Clic derecho sobre el archivo → "Ejecutar con PowerShell"
#  
#  O desde una terminal PowerShell:
#    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#    .\install_ffmpeg_windows.ps1
# ══════════════════════════════════════════════════════════════════════════════

$ErrorActionPreference = "Stop"

# ── Configuración ─────────────────────────────────────────────────────────────
$ffmpegVersion  = "7.1"
$downloadUrl    = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
$installDir     = "$env:LOCALAPPDATA\ffmpeg"        # C:\Users\TU_USUARIO\AppData\Local\ffmpeg
$zipPath        = "$env:TEMP\ffmpeg_download.zip"
$binPath        = "$installDir\bin"

# ── Colores helpers ───────────────────────────────────────────────────────────
function Write-Step   { param($msg) Write-Host "`n▶  $msg" -ForegroundColor Cyan }
function Write-OK     { param($msg) Write-Host "   ✅  $msg" -ForegroundColor Green }
function Write-Warn   { param($msg) Write-Host "   ⚠   $msg" -ForegroundColor Yellow }
function Write-Err    { param($msg) Write-Host "   ❌  $msg" -ForegroundColor Red }

# ── Banner ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "══════════════════════════════════════════" -ForegroundColor Magenta
Write-Host "   Instalador de FFmpeg para Windows      " -ForegroundColor Magenta
Write-Host "══════════════════════════════════════════" -ForegroundColor Magenta

# ── ¿Ya está instalado? ───────────────────────────────────────────────────────
Write-Step "Verificando si FFmpeg ya está instalado..."
$existing = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($existing) {
    $ver = & ffmpeg -version 2>&1 | Select-Object -First 1
    Write-OK "FFmpeg ya está disponible en el PATH:"
    Write-Host "   $($existing.Source)" -ForegroundColor Gray
    Write-Host "   $ver"               -ForegroundColor Gray
    Write-Host ""
    Read-Host "   Presiona Enter para cerrar"
    exit 0
}

# ── Crear carpeta de instalación ──────────────────────────────────────────────
Write-Step "Preparando carpeta de instalación: $installDir"
if (Test-Path $installDir) {
    Write-Warn "La carpeta ya existe, se sobreescribirá el contenido"
} else {
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
}
Write-OK "Carpeta lista"

# ── Descarga ──────────────────────────────────────────────────────────────────
Write-Step "Descargando FFmpeg (build oficial BtbN/FFmpeg-Builds)..."
Write-Host "   URL : $downloadUrl" -ForegroundColor Gray
Write-Host "   Dest: $zipPath"     -ForegroundColor Gray

try {
    # Usar BITS si está disponible (más fiable en entornos corporativos)
    $bitsAvailable = Get-Command Start-BitsTransfer -ErrorAction SilentlyContinue
    if ($bitsAvailable) {
        Start-BitsTransfer -Source $downloadUrl -Destination $zipPath -DisplayName "Descargando FFmpeg"
    } else {
        $wc = New-Object System.Net.WebClient
        $wc.DownloadFile($downloadUrl, $zipPath)
    }
    Write-OK "Descarga completada ($('{0:N1}' -f ((Get-Item $zipPath).Length / 1MB)) MB)"
} catch {
    Write-Err "Error al descargar: $_"
    Write-Host ""
    Write-Host "   Descarga manual:" -ForegroundColor Yellow
    Write-Host "   1. Ve a: https://github.com/BtbN/FFmpeg-Builds/releases" -ForegroundColor Yellow
    Write-Host "   2. Descarga: ffmpeg-master-latest-win64-gpl.zip" -ForegroundColor Yellow
    Write-Host "   3. Extrae en: $installDir" -ForegroundColor Yellow
    Write-Host "   4. Agrega al PATH: $binPath" -ForegroundColor Yellow
    Read-Host "`n   Presiona Enter para cerrar"
    exit 1
}

# ── Extracción ────────────────────────────────────────────────────────────────
Write-Step "Extrayendo archivos..."
$extractTemp = "$env:TEMP\ffmpeg_extract"
if (Test-Path $extractTemp) { Remove-Item $extractTemp -Recurse -Force }

Expand-Archive -Path $zipPath -DestinationPath $extractTemp -Force

# El ZIP tiene una subcarpeta raíz (ffmpeg-master-latest-win64-gpl)
# Mover su contenido directamente a $installDir
$innerFolder = Get-ChildItem -Path $extractTemp -Directory | Select-Object -First 1
if ($innerFolder) {
    Copy-Item -Path "$($innerFolder.FullName)\*" -Destination $installDir -Recurse -Force
} else {
    Copy-Item -Path "$extractTemp\*" -Destination $installDir -Recurse -Force
}

# Limpiar temporales
Remove-Item $extractTemp -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $zipPath     -Force         -ErrorAction SilentlyContinue

Write-OK "Extracción completada"

# ── Verificar que ffmpeg.exe existe ──────────────────────────────────────────
Write-Step "Buscando ffmpeg.exe en $installDir..."
$ffmpegExe = Get-ChildItem -Path $installDir -Recurse -Filter "ffmpeg.exe" |
             Select-Object -First 1

if (-not $ffmpegExe) {
    Write-Err "No se encontró ffmpeg.exe después de la extracción"
    Write-Host "   Contenido de $installDir :" -ForegroundColor Gray
    Get-ChildItem $installDir | ForEach-Object { Write-Host "     $_" -ForegroundColor Gray }
    Read-Host "`n   Presiona Enter para cerrar"
    exit 1
}

$actualBinPath = $ffmpegExe.DirectoryName
Write-OK "ffmpeg.exe encontrado en: $actualBinPath"

# ── Agregar al PATH del usuario (sin necesitar Administrador) ─────────────────
Write-Step "Agregando al PATH del usuario..."

$currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")

if ($currentPath -split ";" | Where-Object { $_ -eq $actualBinPath }) {
    Write-Warn "La ruta ya estaba en el PATH del usuario. No se modifica."
} else {
    $newPath = $currentPath.TrimEnd(";") + ";" + $actualBinPath
    [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
    Write-OK "PATH actualizado correctamente"
    Write-Warn "Deberás REINICIAR la terminal (o abrir una nueva) para que el PATH surta efecto"
}

# ── Prueba inmediata usando la ruta directa ───────────────────────────────────
Write-Step "Verificando instalación..."
$testResult = & "$actualBinPath\ffmpeg.exe" -version 2>&1 | Select-Object -First 1
Write-OK "FFmpeg instalado correctamente:"
Write-Host "   $testResult" -ForegroundColor Gray
Write-Host ""
Write-Host "══════════════════════════════════════════" -ForegroundColor Green
Write-Host "   ✅  Instalación completada              " -ForegroundColor Green
Write-Host "══════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "   Ruta de instalación : $installDir"       -ForegroundColor White
Write-Host "   Ejecutables en      : $actualBinPath"    -ForegroundColor White
Write-Host ""
Write-Host "   IMPORTANTE: Abre una nueva terminal (cmd/PowerShell)"   -ForegroundColor Yellow
Write-Host "   para que el PATH actualizado esté disponible."           -ForegroundColor Yellow
Write-Host ""

Read-Host "   Presiona Enter para cerrar"
