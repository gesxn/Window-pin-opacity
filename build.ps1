$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ProjectDir ".venv-build"
$OutputDir = Join-Path $ProjectDir "dist"

if (-not (Test-Path (Join-Path $VenvDir "Scripts\python.exe"))) {
    py -m venv $VenvDir
}

$Python = Join-Path $VenvDir "Scripts\python.exe"
& $Python -m pip install --disable-pip-version-check --upgrade pip pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось установить зависимости сборки. Код: $LASTEXITCODE"
}
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "WindowPinner" `
    --distpath $OutputDir `
    --workpath (Join-Path $ProjectDir "build") `
    --specpath $ProjectDir `
    (Join-Path $ProjectDir "window_pinner.py")
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось собрать WindowPinner.exe. Код: $LASTEXITCODE"
}

Write-Host "Готово: $(Join-Path $OutputDir 'WindowPinner.exe')"

