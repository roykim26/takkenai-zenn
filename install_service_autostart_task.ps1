$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskName = "zenn-bot-service-autostart"
$BatPath = Join-Path $ProjectDir "start_service.bat"
$StartupShortcutPath = Join-Path ([Environment]::GetFolderPath("Startup")) "zenn-bot-service-autostart.lnk"

if (-not (Test-Path $BatPath)) {
    throw "start_service.bat not found: $BatPath"
}

function Install-StartupShortcut {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($StartupShortcutPath)
    $shortcut.TargetPath = $BatPath
    $shortcut.WorkingDirectory = $ProjectDir
    $shortcut.WindowStyle = 7
    $shortcut.Description = "Start zenn-bot local service loop when Windows user logs on."
    $shortcut.Save()

    [PSCustomObject]@{
        Mode = "StartupShortcut"
        Path = $StartupShortcutPath
    }
}

$Action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$BatPath`"" `
    -WorkingDirectory $ProjectDir

$LogonTrigger = New-ScheduledTaskTrigger -AtLogOn

$Settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Days 30)

try {
    $StartupTrigger = New-ScheduledTaskTrigger -AtStartup
    $Principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Highest

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger @($StartupTrigger, $LogonTrigger) `
        -Settings $Settings `
        -Principal $Principal `
        -Description "Start zenn-bot local service loop at Windows startup/logon." `
        -Force | Out-Null
} catch {
    Write-Warning "High-privilege startup task registration failed, falling back to current-user logon trigger: $($_.Exception.Message)"

    try {
        Register-ScheduledTask `
            -TaskName $TaskName `
            -Action $Action `
            -Trigger $LogonTrigger `
            -Settings $Settings `
            -Description "Start zenn-bot local service loop when the current user logs on." `
            -Force | Out-Null
    } catch {
        Write-Warning "Current-user scheduled task registration failed, installing Startup folder shortcut: $($_.Exception.Message)"
        Install-StartupShortcut
        exit 0
    }
}

Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
