# ChestZip kurulumu (Windows, PowerShell):
#   irm https://raw.githubusercontent.com/mesutozansoftware/chestzip/main/install.ps1 | iex
#
# Son sürümün kurulum programını indirir, SHA-256 özetini doğrular ve
# yönetici yetkisi gerektirmeden (yalnızca bu kullanıcı için) sessizce kurar.
# Belirli sürüm için önce:  $env:CHESTZIP_VERSION = "1.0.0"

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Repo = "mesutozansoftware/chestzip"
if ($env:CHESTZIP_VERSION) {
    $Base = "https://github.com/$Repo/releases/download/v$($env:CHESTZIP_VERSION.TrimStart('v'))"
} else {
    $Base = "https://github.com/$Repo/releases/latest/download"
}

function Say($msg) { Write-Host "==> $msg" -ForegroundColor Yellow }

if (-not [Environment]::Is64BitOperatingSystem) { throw "ChestZip 64 bit Windows gerektirir." }

$Tmp = Join-Path ([IO.Path]::GetTempPath()) ("chestzip-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $Tmp | Out-Null
try {
    Say "Sürüm bilgisi alınıyor..."
    $Sums = (Invoke-WebRequest -UseBasicParsing "$Base/SHA256SUMS.txt").Content
    if ($Sums -is [byte[]]) { $Sums = [Text.Encoding]::UTF8.GetString($Sums) }
    $Line = ($Sums -split "`n") | Where-Object { $_ -match "setup-windows-x64\.exe\s*$" } | Select-Object -First 1
    if (-not $Line) { throw "Windows kurulum programı bulunamadı." }
    $Expected, $File = ($Line.Trim() -split "\s+", 2)
    $File = $File.TrimStart("*")

    Say "İndiriliyor: $File"
    $Path = Join-Path $Tmp $File
    Invoke-WebRequest -UseBasicParsing "$Base/$File" -OutFile $Path
    $Actual = (Get-FileHash -Algorithm SHA256 $Path).Hash
    if ($Actual -ne $Expected.ToUpper()) { throw "SHA-256 doğrulaması başarısız! Dosya bozuk veya değiştirilmiş." }
    Say "SHA-256 doğrulandı. Kuruluyor..."

    $p = Start-Process -FilePath $Path -Wait -PassThru -ArgumentList `
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/SP-"
    if ($p.ExitCode -ne 0) { throw "Kurulum başarısız (çıkış kodu $($p.ExitCode))." }
    Say "Tamamlandı. ChestZip Başlat menüsünde; .chz dosyaları ChestZip ile açılır."
} finally {
    Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}
