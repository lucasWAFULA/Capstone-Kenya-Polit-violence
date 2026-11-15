[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z][a-z0-9-]{4,28}[a-z0-9]$')]
    [string]$ProjectId,
    [string]$Region = 'africa-south1',
    [string]$Repository = 'severity-models',
    [string]$BuildServiceAccount = 'severity-build',
    [string]$RuntimeServiceAccount = 'severity-runtime'
)

$ErrorActionPreference = 'Stop'
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw 'gcloud CLI is required. Install it, authenticate, and rerun this script.'
}

gcloud projects describe $ProjectId --format='value(projectId)' | Out-Null
gcloud config set project $ProjectId | Out-Null
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com iam.googleapis.com --project=$ProjectId

$repositoryExists = gcloud artifacts repositories describe $Repository --location=$Region --project=$ProjectId --format='value(name)' 2>$null
if (-not $repositoryExists) {
    gcloud artifacts repositories create $Repository --repository-format=docker --location=$Region --description='Kenya event severity production images' --project=$ProjectId
}

foreach ($account in @($BuildServiceAccount, $RuntimeServiceAccount)) {
    $email = "$account@$ProjectId.iam.gserviceaccount.com"
    $exists = gcloud iam service-accounts describe $email --project=$ProjectId --format='value(email)' 2>$null
    if (-not $exists) {
        gcloud iam service-accounts create $account --display-name=$account --project=$ProjectId
    }
}

$buildEmail = "$BuildServiceAccount@$ProjectId.iam.gserviceaccount.com"
$runtimeEmail = "$RuntimeServiceAccount@$ProjectId.iam.gserviceaccount.com"
foreach ($role in @('roles/artifactregistry.writer', 'roles/run.admin', 'roles/logging.logWriter')) {
    gcloud projects add-iam-policy-binding $ProjectId --member="serviceAccount:$buildEmail" --role=$role --condition=None --quiet | Out-Null
}
gcloud iam service-accounts add-iam-policy-binding $runtimeEmail --member="serviceAccount:$buildEmail" --role='roles/iam.serviceAccountUser' --project=$ProjectId --quiet | Out-Null

$activeAccount = gcloud auth list --filter=status:ACTIVE --format='value(account)' | Select-Object -First 1
if (-not $activeAccount) {
    throw 'No active gcloud account. Run gcloud auth login first.'
}
$activeMember = if ($activeAccount.EndsWith('.gserviceaccount.com')) { "serviceAccount:$activeAccount" } else { "user:$activeAccount" }
gcloud iam service-accounts add-iam-policy-binding $buildEmail --member=$activeMember --role='roles/iam.serviceAccountUser' --project=$ProjectId --quiet | Out-Null

Write-Host "GCP bootstrap complete for $ProjectId in $Region."
Write-Host "Build identity: $buildEmail"
Write-Host "Runtime identity: $runtimeEmail (no project roles granted)"
