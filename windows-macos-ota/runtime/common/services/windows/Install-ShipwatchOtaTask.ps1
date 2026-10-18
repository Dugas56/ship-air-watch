param(
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [Parameter(Mandatory=$true)][string]$AgentPath,
    [Parameter(Mandatory=$true)][string]$ConfigPath,
    [Parameter(Mandatory=$true)][string]$EnrollmentMarkerPath
)
$ErrorActionPreference = 'Stop'
$paths = @($PythonPath, $AgentPath, $ConfigPath, $EnrollmentMarkerPath) | ForEach-Object {
    $resolved = [IO.Path]::GetFullPath($_)
    if ($resolved -match '["\r\n]') { throw 'Paths may not contain quotes or line breaks.' }
    $resolved
}
$python, $agent, $config, $marker = $paths
if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
    throw 'Refusing to register OTA polling before signed enrollment is confirmed.'
}
foreach ($file in @($python, $agent, $config)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Required OTA file not found: $file" }
}
$identity = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
if (-not $identity.device_id -or -not $identity.api_url.StartsWith('https://')) {
    throw 'OTA agent configuration is incomplete or does not use HTTPS.'
}
$taskName = 'Shipwatch OTA Check'
$action = New-ScheduledTaskAction -Execute $python -Argument ('"{0}" --config "{1}"' -f $agent, $config)
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Output 'Shipwatch OTA scheduled task registered.'
