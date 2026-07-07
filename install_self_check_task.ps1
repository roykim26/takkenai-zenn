$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskName = "zenn-bot-publish-self-check"
$BatPath = Join-Path $ProjectDir "run_self_check.bat"

if (-not (Test-Path $BatPath)) {
    throw "run_self_check.bat not found: $BatPath"
}

$Action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$BatPath`"" `
    -WorkingDirectory $ProjectDir

$Trigger1500 = New-ScheduledTaskTrigger -Daily -At "15:00"
$Trigger1800 = New-ScheduledTaskTrigger -Daily -At "18:00"
$Triggers = @($Trigger1500, $Trigger1800)

$Settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Triggers `
    -Settings $Settings `
    -Description "Check today's Feishu publishing records at 15:00 and 18:00, notify if not published, then retry safe records." `
    -Force | Out-Null

Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
