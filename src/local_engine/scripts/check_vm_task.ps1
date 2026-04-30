# 检查 VM 中 computer_server 的运行状态
# 用法: .\check_vm_task.ps1 -VMName "UseIt-Dev-VM" -Username "useit" -Password "12345678"

param(
    [string]$VMName = "UseIt-Dev-VM",
    [string]$Username = "useit", 
    [string]$Password = "12345678"
)

$secPassword = ConvertTo-SecureString $Password -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential ($Username, $secPassword)

Write-Host "============================================================"
Write-Host "  Checking computer_server status in VM: $VMName"
Write-Host "============================================================"

$result = Invoke-Command -VMName $VMName -Credential $cred -ScriptBlock {
    Write-Host "`n=== 1. Scheduled Task Info ==="
    $task = Get-ScheduledTask -TaskName "UseItComputerServer" -ErrorAction SilentlyContinue
    if ($task) {
        Write-Host "Task Name: $($task.TaskName)"
        Write-Host "State: $($task.State)"
        
        $taskInfo = Get-ScheduledTaskInfo -TaskName "UseItComputerServer"
        Write-Host "Last Run Time: $($taskInfo.LastRunTime)"
        Write-Host "Last Result: $($taskInfo.LastTaskResult)"
        Write-Host "Next Run Time: $($taskInfo.NextRunTime)"
        
        # 获取 Principal 信息
        $principal = $task.Principal
        Write-Host "Run As User: $($principal.UserId)"
        Write-Host "Logon Type: $($principal.LogonType)"
        Write-Host "Run Level: $($principal.RunLevel)"
        
        # 获取 Trigger 信息
        $triggers = $task.Triggers
        foreach ($trigger in $triggers) {
            Write-Host "Trigger Type: $($trigger.CimClass.CimClassName)"
        }
    } else {
        Write-Host "Task 'UseItComputerServer' not found!"
    }
    
    Write-Host "`n=== 2. Process Info ==="
    $process = Get-Process -Name "computer_server" -ErrorAction SilentlyContinue
    if ($process) {
        Write-Host "PID: $($process.Id)"
        Write-Host "Session ID: $($process.SessionId)"
        Write-Host "Start Time: $($process.StartTime)"
        Write-Host "CPU: $($process.CPU)"
        Write-Host "Memory (MB): $([math]::Round($process.WorkingSet64 / 1MB, 2))"
        
        # Session ID 0 = 非交互式 (SYSTEM), 1+ = 用户会话
        if ($process.SessionId -eq 0) {
            Write-Host "`n*** WARNING: Process is running in Session 0 (non-interactive)! ***"
            Write-Host "*** This is why screenshot and cursor operations fail! ***"
        } else {
            Write-Host "`nProcess is running in Session $($process.SessionId) (interactive) - OK"
        }
    } else {
        Write-Host "Process 'computer_server' not running!"
    }
    
    Write-Host "`n=== 3. Current User Sessions ==="
    query user 2>$null | ForEach-Object { Write-Host $_ }
    
    Write-Host "`n=== 4. Who is logged in? ==="
    $loggedInUsers = Get-WmiObject -Class Win32_ComputerSystem | Select-Object -ExpandProperty UserName
    Write-Host "Currently logged in: $loggedInUsers"
}

Write-Host "`n============================================================"
Write-Host "  Check Complete"
Write-Host "============================================================"




