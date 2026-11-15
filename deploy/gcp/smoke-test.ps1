[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ServiceUrl,
    [switch]$Authenticated
)

$ErrorActionPreference = 'Stop'
$headers = @{}
if ($Authenticated) {
    $token = gcloud auth print-identity-token --audiences=$ServiceUrl
    if ($LASTEXITCODE -ne 0) { throw 'Could not obtain an identity token.' }
    $headers.Authorization = "Bearer $token"
}

$ready = $null
$deadline = (Get-Date).AddSeconds(90)
do {
    try {
        $ready = Invoke-RestMethod -Method Get -Uri "$ServiceUrl/health/ready" -Headers $headers -TimeoutSec 10
    }
    catch {
        if ((Get-Date) -ge $deadline) { throw }
        Start-Sleep -Seconds 2
    }
} while (-not $ready -and (Get-Date) -lt $deadline)
if (-not $ready) { throw 'Service did not become ready within 90 seconds.' }
if ($ready.status -ne 'ready') { throw 'Readiness check failed.' }

$payload = @{
    event_date = '2026-09-20'; disorder_type = 'Political violence'; event_type = 'Battles'
    sub_event_type = 'Armed clash'; admin1 = 'Nairobi'; admin2 = 'Nairobi'; inter1 = 1
    interaction = 12; civilian_targeting = $null; county_events_previous_30_days = 8
    county_events_previous_90_days = 20; violent_events_previous_30_days = 4
    previous_high_severity_events_in_county = 1; days_since_previous_event_in_county = 2
    actor_previous_event_count = 15
} | ConvertTo-Json
$prediction = Invoke-RestMethod -Method Post -Uri "$ServiceUrl/v1/predict" -Headers $headers -ContentType 'application/json' -Body $payload
Write-Host "Ready model version: $($ready.model_version)"
Write-Host "Prediction: $($prediction.severity); request ID: $($prediction.request_id)"
