# Otacon Lite - repair chat from Windows PowerShell (no line wrapping).
# Usage: right-click -> Run with PowerShell, OR paste the whole file into PowerShell.
$ErrorActionPreference = "Stop"
$Distro = "Ubuntu-22.04"
$User = "xofyerg"

Write-Host "Pulling latest Otacon Lite into WSL..." -ForegroundColor Cyan
wsl.exe -d $Distro -u $User -e git -C /home/xofyerg/otacon-ai-ecosystem pull --ff-only

Write-Host "Pulling Ollama model qwen2.5:7b (this can take a few minutes)..." -ForegroundColor Cyan
wsl.exe -d $Distro -u $User -e ollama pull qwen2.5:7b

Write-Host "Restarting otacon service..." -ForegroundColor Cyan
wsl.exe -d $Distro -u root -e systemctl restart otacon

Start-Sleep -Seconds 3

Write-Host "Testing chat..." -ForegroundColor Cyan
$body = '{"agent":{"id":"agent_001","display_name":"Aria","voice_id":"voice_aria"},"message":"hi","conversation_id":"repair1"}'
$tmp = Join-Path $env:TEMP "otacon-chat-repair.json"
Set-Content -Path $tmp -Value $body -Encoding Ascii
curl.exe -s -X POST "http://127.0.0.1:5757/api/chat_with_agent" -H "Content-Type: application/json" --data-binary "@$tmp"
Write-Host ""
Write-Host "If you see a JSON field named text, chat is fixed. Then Ctrl+F5 the browser." -ForegroundColor Green
