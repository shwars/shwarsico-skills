param([switch]$SetupOnly)
$ErrorActionPreference = 'Stop'
$appBase = $PSScriptRoot
$envDirectory = Join-Path $appBase '.venv'
$gamePython = Join-Path $envDirectory 'Scripts/python.exe'
if (-not (Test-Path -LiteralPath $gamePython)) {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) { & $launcher.Source -3.11 -m venv $envDirectory }
    else { & python -m venv $envDirectory }
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.11, then run again.' }
}
& $gamePython -c "import sys; assert sys.version_info[:2] == (3, 11), 'Python 3.11 is required'"
if ($LASTEXITCODE -ne 0) { throw 'This environment requires Python 3.11.' }
$pygameReady = & $gamePython -c "import importlib.metadata as m; print(any((d.metadata['Name'] or '').lower() == 'pygame' and d.version == '2.6.1' for d in m.distributions()))"
if (($pygameReady | Out-String).Trim() -ne 'True') {
    & $gamePython -m pip install -r (Join-Path $appBase 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Could not install pygame. Check the network and run again.' }
}
if (-not $SetupOnly) {
    & $gamePython (Join-Path $appBase 'main.py')
    exit $LASTEXITCODE
}
