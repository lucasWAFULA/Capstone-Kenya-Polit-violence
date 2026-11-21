[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z][a-z0-9-]{4,28}[a-z0-9]$')]
    [string]$ProjectId,
    [string]$Region = 'africa-south1',
    [string]$Repository = 'severity-models',
    [string]$Service = 'kenya-event-severity',
    [string]$BuildServiceAccount = 'severity-build',
    [string]$RuntimeServiceAccount = 'severity-runtime',
    [switch]$AllowUnauthenticated,
    [switch]$Private
)

$ErrorActionPreference = 'Stop'
if ($Private -and $AllowUnauthenticated) { throw 'Choose either -Private or -AllowUnauthenticated, not both.' }
$accessFlag = if ($Private) { '--no-allow-unauthenticated' } else { '--allow-unauthenticated' }
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$manifest = Join-Path $projectRoot 'artifacts\production\manifest.json'
if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
    throw "Production manifest is missing: $manifest. Train the models before deployment."
}
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw 'gcloud CLI is required. Install it, authenticate, and rerun this script.'
}

$buildEmail = "$BuildServiceAccount@$ProjectId.iam.gserviceaccount.com"
$runtimeEmail = "$RuntimeServiceAccount@$ProjectId.iam.gserviceaccount.com"
Push-Location $projectRoot
try {
    gcloud builds submit . `
        --project=$ProjectId `
        --region=$Region `
        --service-account="projects/$ProjectId/serviceAccounts/$buildEmail" `
        --config=cloudbuild.yaml `
        --substitutions="_REGION=$Region,_REPOSITORY=$Repository,_SERVICE=$Service,_RUNTIME_SERVICE_ACCOUNT=$runtimeEmail,_ACCESS_FLAG=$accessFlag"
    if ($LASTEXITCODE -ne 0) { throw "Cloud Build failed with exit code $LASTEXITCODE." }
}
finally {
    Pop-Location
}

$serviceUrl = gcloud run services describe $Service --project=$ProjectId --region=$Region --format='value(status.url)'
Write-Host "Deployment complete: $serviceUrl"
if ($Private) {
    Write-Host "Private smoke test: gcloud run services proxy $Service --project=$ProjectId --region=$Region"
}
else {
    Write-Host 'The website and API are public. Application-level authentication is not implemented.'
}
