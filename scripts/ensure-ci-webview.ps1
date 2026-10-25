$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$runtimeFound=$false
foreach($runtimeHive in @([Microsoft.Win32.RegistryHive]::LocalMachine,[Microsoft.Win32.RegistryHive]::CurrentUser)){
 foreach($runtimeView in @([Microsoft.Win32.RegistryView]::Registry32,[Microsoft.Win32.RegistryView]::Registry64)){
  $runtimeBase=[Microsoft.Win32.RegistryKey]::OpenBaseKey($runtimeHive,$runtimeView)
  try{$runtimeKey=$runtimeBase.OpenSubKey('Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}');if($runtimeKey){try{if($runtimeKey.GetValue('pv') -and $runtimeKey.GetValue('pv') -ne '0.0.0.0'){$runtimeFound=$true}}finally{$runtimeKey.Dispose()}}}finally{$runtimeBase.Dispose()}
 }
}
if($runtimeFound){Write-Output 'WebView2 Runtime already available';return}
if($env:GITHUB_ACTIONS -ne 'true'){throw 'This prerequisite setup is restricted to the disposable CI runner.'}
$runtimeProject=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtimeProduct=Get-Content -LiteralPath (Join-Path $runtimeProject 'installer\inno\product.json') -Raw|ConvertFrom-Json
$runtimeBootstrap=Join-Path $runtimeProject $runtimeProduct.Bootstrapper
if((Get-FileHash -LiteralPath $runtimeBootstrap -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'f414de01c4680f0bb0694d1ea7803c6968f3a81bf6bad01b89bfc65dce14c2a2'){throw 'Runtime bootstrapper checksum mismatch.'}
$runtimeSignature=Get-AuthenticodeSignature -LiteralPath $runtimeBootstrap
if($runtimeSignature.Status -ne 'Valid' -or $runtimeSignature.SignerCertificate.Subject -notmatch 'Microsoft Corporation'){throw 'Runtime publisher verification failed.'}
$runtimeProcess=Start-Process -FilePath $runtimeBootstrap -ArgumentList @('/silent','/install') -WindowStyle Hidden -Wait -PassThru
if($runtimeProcess.ExitCode -notin @(0,3010)){throw 'CI runtime prerequisite setup failed.'}
