$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
try {
    if (Get-Process -Name LEGOAtelier,BrickLabo -ErrorAction SilentlyContinue) {
        throw 'Fermez le logiciel avant de lancer le correctif.'
    }
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = 'Choisissez le dossier du logiciel contenant atelier et LEGOAtelier.exe ou BrickLabo.exe.'
    $dialog.ShowNewFolderButton = $false
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { exit 0 }
    $target = $dialog.SelectedPath
    $legacy = Join-Path $target 'LEGOAtelier.exe'
    $launcher = Join-Path $target 'BrickLabo.exe'
    if ((!(Test-Path -LiteralPath $legacy) -and !(Test-Path -LiteralPath $launcher)) -or !(Test-Path -LiteralPath (Join-Path $target 'atelier\app.py'))) {
        throw 'Choisissez le dossier qui contient le lanceur du logiciel et atelier\app.py.'
    }
    $backup = Join-Path $target ('sauvegarde-correctif-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    New-Item -ItemType Directory -Path $backup | Out-Null
    $changes = @()
    foreach ($file in (Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'atelier') -Filter '*.py' -File)) {
        $changes += @{ Source=$file.FullName; Relative=('atelier\' + $file.Name) }
    }
    foreach ($file in (Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'lanceur') -File)) {
        $changes += @{ Source=$file.FullName; Relative=$file.Name }
    }
    foreach ($file in (Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'ressources') -File)) {
        $changes += @{ Source=$file.FullName; Relative=('ressources\' + $file.Name) }
    }
    foreach ($name in @('SOURCES_ET_LICENCES.html','VERSION.txt','AIDE.html','NOUVEAUTES.txt','PROJET_GITHUB.url')) {
        $changes += @{ Source=(Join-Path $PSScriptRoot $name); Relative=$name }
    }
    $licencesFolder = Join-Path $PSScriptRoot 'licences'
    if (Test-Path -LiteralPath $licencesFolder) {
        foreach ($file in (Get-ChildItem -LiteralPath $licencesFolder -Recurse -File)) {
            $changes += @{ Source=$file.FullName; Relative=('licences\' + $file.FullName.Substring($licencesFolder.Length + 1)) }
        }
    }
    if (!(Test-Path -LiteralPath $launcher) -and !(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'lanceur\BrickLabo.exe'))) { $changes += @{ Source=$legacy; Relative='BrickLabo.exe' } }
    $added = @()
    foreach ($change in $changes) {
        $destination = Join-Path $target $change.Relative
        if (Test-Path -LiteralPath $destination) {
            $saved = Join-Path $backup $change.Relative
            New-Item -ItemType Directory -Path (Split-Path $saved -Parent) -Force | Out-Null
            Copy-Item -LiteralPath $destination -Destination $saved
        } else { $added += $destination }
    }
    $obsolete = @(Get-ChildItem -LiteralPath $target -Filter 'NOUVEAUTES_v*.txt' -File)
    foreach ($file in $obsolete) { Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $backup $file.Name) }
    try {
        foreach ($change in $changes) {
            New-Item -ItemType Directory -Path (Split-Path (Join-Path $target $change.Relative) -Parent) -Force | Out-Null
            Copy-Item -LiteralPath $change.Source -Destination (Join-Path $target $change.Relative) -Force
        }
        foreach ($file in $obsolete) { Remove-Item -LiteralPath $file.FullName }
    } catch {
        foreach ($file in $obsolete) { Copy-Item -LiteralPath (Join-Path $backup $file.Name) -Destination $file.FullName -Force }
        foreach ($change in $changes) {
            $saved = Join-Path $backup $change.Relative
            if (Test-Path -LiteralPath $saved) { Copy-Item -LiteralPath $saved -Destination (Join-Path $target $change.Relative) -Force }
        }
        foreach ($path in $added) { if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path } }
        throw
    }
    [System.Windows.Forms.MessageBox]::Show('BrickLabo by SDU7 est pret. Vos donnees sont conservees. Relancez BrickLabo.exe.','BrickLabo by SDU7') | Out-Null
} catch {
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message,'Correctif non applique') | Out-Null
    exit 1
}
