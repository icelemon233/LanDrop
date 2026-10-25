$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($env:GITHUB_ACTIONS -ne 'true' -or $env:GITHUB_REPOSITORY -ne 'icelemon233/LanDrop' -or -not $env:GH_TOKEN){throw 'Use the authorized LanDrop maintenance workflow.'}
$ciRepo=$env:GITHUB_REPOSITORY
$ciVersion=(Get-Content landrop/version.json -Raw | ConvertFrom-Json).version
$ciDeadline=[DateTime]::UtcNow.AddMinutes(10)
do{
  $ciReleases=@((& gh api ('repos/'+$ciRepo+'/releases?per_page=100') | ConvertFrom-Json))
  if($LASTEXITCODE -ne 0){throw 'Release inventory failed.'}
  $ciRelease=@($ciReleases | Where-Object { -not $_.draft -and $_.tag_name -eq ('v'+$ciVersion) })
  $ciRuns=& gh api ('repos/'+$ciRepo+'/actions/workflows/check.yml/runs?per_page=100') | ConvertFrom-Json
  if($LASTEXITCODE -ne 0){throw 'Build inventory failed.'}
  $ciOlderRuns=@($ciRuns.workflow_runs | Where-Object {$_.status -ne 'completed' -and $_.head_sha -ne $env:GITHUB_SHA})
  if($ciRelease.Count -eq 1 -and $ciOlderRuns.Count -eq 0){break}
  if([DateTime]::UtcNow -gt $ciDeadline){throw 'Wait for verified publication and older package-producing builds before cleanup.'}
  Start-Sleep -Seconds 15
}while($true)
$ciSetup=@($ciRelease[0].assets | Where-Object name -eq ('LanDrop-v'+$ciVersion+'-windows-x64-setup.exe'))
if($ciSetup.Count -ne 1 -or $ciSetup[0].digest -notmatch '^sha256:[a-f0-9]{64}$'){throw 'The retained installer has no verified release digest.'}
# Distribution now comes from the verified Release. CI still validates builds,
# but no longer uploads additional installer copies under a generic name.
$ciQuery='.artifacts[] | select(.name == "LanDrop-Windows-x64") | .id'
$ciIds=@(& gh api --paginate ('repos/'+$ciRepo+'/actions/artifacts?per_page=100') --jq $ciQuery)
if($LASTEXITCODE -ne 0){throw 'CI package inventory failed.'}
foreach($ciId in $ciIds){
  if($ciId -notmatch '^\d+$'){throw 'Invalid artifact identity.'}
  $ciArtifact=& gh api ('repos/'+$ciRepo+'/actions/artifacts/'+$ciId) | ConvertFrom-Json
  if($LASTEXITCODE -ne 0 -or $ciArtifact.name -ne 'LanDrop-Windows-x64'){throw 'Unexpected artifact; keep unrelated CI output.'}
  & gh api --method DELETE ('repos/'+$ciRepo+'/actions/artifacts/'+$ciId)
  if($LASTEXITCODE -ne 0){throw ('CI package deletion failed: '+$ciId)}
}
$ciRemaining=@(& gh api --paginate ('repos/'+$ciRepo+'/actions/artifacts?per_page=100') --jq $ciQuery)
if($LASTEXITCODE -ne 0 -or $ciRemaining.Count -ne 0){throw 'Obsolete CI installer copies remain.'}
Write-Output ('Removed '+$ciIds.Count+' duplicate CI installer archives; retained verified Release v'+$ciVersion+'.')
