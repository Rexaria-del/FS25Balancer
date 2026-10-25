$log = Join-Path $env:APPDATA 'FS25Balancer\crash.log'
if (Test-Path $log) { Remove-Item $log -Force }
Start-Process -FilePath C:\FS25Balancer\dist\FS25Balancer.exe
Start-Sleep -Seconds 20
Write-Output '=====JS====='
if (Test-Path $log) { Get-Content $log | Select-String -SimpleMatch '[js]' | ForEach-Object { $_.Line } } else { Write-Output 'no crash.log' }
Get-Process -Name FS25Balancer -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object Responding | Format-List
Stop-Process -Name FS25Balancer -Force -ErrorAction SilentlyContinue
