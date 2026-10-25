param(
  [Parameter(Mandatory)][string]$Version,
  [Parameter(Mandatory)][string]$Title,
  [Parameter(Mandatory)][string]$NotesFile,
  [Parameter(Mandatory)][string[]]$Files,
  [switch]$KeepLatestOnly
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($Version -notmatch '^\d+\.\d+\.\d+$'){throw 'Use a semantic application version.'}
if(-not $env:GITHUB_REPOSITORY -or -not $env:GH_TOKEN){throw 'Run with the repository release identity and GitHub token.'}
$publishRepo=$env:GITHUB_REPOSITORY
$publishTag='v'+$Version
$publishCommit=(& git rev-parse HEAD).Trim()
$publishTagCommit=(& git rev-parse ($publishTag+'^{}')).Trim()
if($LASTEXITCODE -ne 0 -or $publishTagCommit -ne $publishCommit){throw 'Release tag and verified source commit differ.'}
foreach($publishFile in $Files){if(-not (Test-Path -LiteralPath $publishFile -PathType Leaf)){throw ('Missing release asset: '+$publishFile)}}
$publishReleases=@((& gh api ('repos/'+$publishRepo+'/releases?per_page=100') | ConvertFrom-Json))
if($LASTEXITCODE -ne 0){throw 'Release inventory failed.'}
$publishExisting=@($publishReleases | Where-Object tag_name -eq $publishTag)
if($publishExisting.Count -gt 1 -or ($publishExisting.Count -eq 1 -and -not $publishExisting[0].draft)){throw 'A published version cannot be overwritten; increment the application version.'}
if($publishExisting.Count -eq 0){
  & gh release create $publishTag --repo $publishRepo --draft --verify-tag --title $Title --notes-file $NotesFile
  if($LASTEXITCODE -ne 0){throw 'Release draft creation failed.'}
}
& gh release upload $publishTag @Files --repo $publishRepo --clobber
if($LASTEXITCODE -ne 0){throw 'Release upload failed.'}
$publishDrafts=@((& gh api ('repos/'+$publishRepo+'/releases?per_page=100') | ConvertFrom-Json) | Where-Object tag_name -eq $publishTag)
if($LASTEXITCODE -ne 0 -or $publishDrafts.Count -ne 1 -or -not $publishDrafts[0].draft){throw 'Expected the release to remain unpublished during asset verification.'}
$publishDraft=$publishDrafts[0]
foreach($publishFile in $Files){
  $publishName=[IO.Path]::GetFileName($publishFile)
  $publishAsset=@($publishDraft.assets | Where-Object name -eq $publishName)
  $publishDigest='sha256:'+(Get-FileHash -LiteralPath $publishFile -Algorithm SHA256).Hash.ToLowerInvariant()
  if($publishAsset.Count -ne 1 -or $publishAsset[0].digest -ne $publishDigest -or $publishAsset[0].size -ne (Get-Item -LiteralPath $publishFile).Length){throw ('Uploaded asset mismatch: '+$publishName)}
}
& gh release edit $publishTag --repo $publishRepo --draft=false --latest
if($LASTEXITCODE -ne 0){throw 'Verified release publication failed.'}
$publishCurrent=& gh api ('repos/'+$publishRepo+'/releases/tags/'+$publishTag) | ConvertFrom-Json
if($LASTEXITCODE -ne 0 -or $publishCurrent.draft){throw 'Published release could not be confirmed.'}
if($KeepLatestOnly){
  # The latest-only distribution policy is explicitly requested for these apps.
  # Delete release objects/assets only, preserving source commits and Git tags.
  do{
    $publishOld=@((& gh api ('repos/'+$publishRepo+'/releases?per_page=100') | ConvertFrom-Json) | Where-Object id -ne $publishCurrent.id)
    if($LASTEXITCODE -ne 0){throw 'Old release inventory failed.'}
    foreach($publishObsolete in $publishOld){
      & gh api --method DELETE ('repos/'+$publishRepo+'/releases/'+$publishObsolete.id)
      if($LASTEXITCODE -ne 0){throw ('Old release cleanup failed: '+$publishObsolete.tag_name)}
    }
  }while($publishOld.Count -gt 0)
  $publishFinal=@((& gh api ('repos/'+$publishRepo+'/releases?per_page=100') | ConvertFrom-Json))
  if($LASTEXITCODE -ne 0 -or $publishFinal.Count -ne 1 -or $publishFinal[0].id -ne $publishCurrent.id){throw 'Expected only the new release after cleanup.'}
}
Write-Output ('Published and verified '+$publishCurrent.html_url)
