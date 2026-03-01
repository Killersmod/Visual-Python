param(
    [Parameter(Position=0)]
    [string]$File
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Ensure PyQt6 is installed
python -c "import PyQt6" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyQt6..."
    pip install PyQt6>=6.5.0
}

# Set PYTHONPATH so the package can be found
$env:PYTHONPATH = "$scriptDir\src;$env:PYTHONPATH"

# Launch the GUI, optionally opening a file
if ($File) {
    $vpyPath = Resolve-Path $File
    python -c "
import sys
from visualpython.__main__ import main
# Pass file path as argument for the app to pick up
sys.exit(main(['visualpython', r'$vpyPath']))
"
} else {
    python -m visualpython
}
