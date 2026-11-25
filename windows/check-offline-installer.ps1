# Run on an isolated Windows runner. Only the package and its interpreters are blocked.
param([Parameter(Mandatory)][string]$Setup)
$ErrorActionPreference = 'Stop'
$setupFile = (Resolve-Path $Setup).Path
$target = Join-Path $env:RUNNER_TEMP '离线安装 WaxTranslate'
$env:LOCALAPPDATA = Join-Path $env:RUNNER_TEMP 'offline-user'
$rules = @()
function Install-App {
    $p = Start-Process $setupFile -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR=`"$target`"" -Wait -PassThru
    if ($p.ExitCode) { throw "Installer exited $($p.ExitCode)" }
}
try {
    foreach ($program in @($setupFile, "$target\WaxTranslate.exe", "$target\runtime\python.exe", "$target\runtime\pythonw.exe")) {
        $rules += New-NetFirewallRule -DisplayName "WaxTranslate Offline $([guid]::NewGuid())" -Program $program -Direction Outbound -Action Block -Profile Any
    }
    Install-App
    $shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'WaxTranslate.lnk'
    $link = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcut)
    if ($link.TargetPath -ne "$target\WaxTranslate.exe" -or $link.Arguments -ne '--show') { throw 'Missing installed Start menu shortcut' }
    $env:PYTHONUTF8 = '1'
    & "$target\runtime\python.exe" windows\check_launcher.py $target --installed
    if ($LASTEXITCODE) { throw 'Installed launcher failed' }
    & "$target\runtime\python.exe" windows\check_offline_install.py
    if ($LASTEXITCODE) { throw 'Offline reading failed' }
    & "$target\runtime\python.exe" -c "from notebook import Notebook; Notebook().record_lookup(word='catalog', language='en', gloss='目录')"
    if ($LASTEXITCODE) { throw 'Could not seed the real notebook' }
    $book = Join-Path $env:LOCALAPPDATA 'WaxTranslate\notebook.sqlite3'
    $digest = (Get-FileHash $book).Hash
    Install-App
    $uninstall = Start-Process "$target\unins000.exe" -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART' -Wait -PassThru
    if ($uninstall.ExitCode -or (Test-Path "$target\WaxTranslate.exe") -or (Get-FileHash $book).Hash -ne $digest) { throw 'Reinstall/uninstall preservation check failed' }
} finally {
    $rules | Remove-NetFirewallRule
}
