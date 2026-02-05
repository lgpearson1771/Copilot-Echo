$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $repoRoot "src\.venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Virtual environment not found at: $venvPython"
    Write-Host "Create it in VS Code or run: python -m venv src/.venv"
    exit 1
}

& $venvPython @Args
