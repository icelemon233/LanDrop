param([string]$InstallRoot, [string]$QaId, [string]$StateDirectory, [switch]$Removed)
$ErrorActionPreference='Stop'
$StateDirectory=[IO.Path]::GetFullPath($StateDirectory)
if($QaId -notmatch '^[A-Za-z0-9]+$'){throw 'Expected isolated QA identity.'}
$dropName='隔空传 QA '+$QaId
$dropDesktop=Join-Path ([Environment]::GetFolderPath('Desktop')) ($dropName+'.lnk')
$dropMenu=Join-Path ([Environment]::GetFolderPath('Programs')) ($dropName+'\'+$dropName+'.lnk')
if($Removed){
  if((Test-Path -LiteralPath $dropDesktop) -or (Test-Path -LiteralPath $dropMenu)){throw 'QA shortcut remains after uninstall.'}
  Write-Output 'PASS: QA shortcuts removed.'
  return
}
$dropShell=New-Object -ComObject WScript.Shell
foreach($dropPath in @($dropDesktop,$dropMenu)){
  if(-not (Test-Path -LiteralPath $dropPath)){throw 'Expected QA shortcut was not created.'}
  $dropLink=$dropShell.CreateShortcut($dropPath)
  if($dropLink.TargetPath -ne (Join-Path $InstallRoot '隔空传.exe')){throw 'Shortcut target does not match installed app.'}
  if($dropLink.IconLocation -ne ((Join-Path $InstallRoot 'app.ico')+',0')){throw 'Shortcut does not reference the current application icon.'}
  if($dropLink.Arguments -ne ('--state-dir "'+$StateDirectory+'"')){throw 'QA shortcut arguments do not use isolated state.'}
}
Write-Output 'PASS: desktop and Start menu shortcut targets and arguments.'
