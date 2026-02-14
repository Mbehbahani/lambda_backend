# =============================================================================
# Update Lambda Environment Variables
# Updates specific or all environment variables for the Lambda function
# =============================================================================

param(
    [string]$FunctionName = "llm-backend",
    [string]$EnvFile = ".env",
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  Update Lambda Environment Variables" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

# Get script directory
$ScriptDir = Split-Path -Parent $PSCommandPath
$LambdaDir = Split-Path -Parent $ScriptDir
$EnvFilePath = Join-Path $LambdaDir $EnvFile

if (-not (Test-Path $EnvFilePath)) {
    Write-Host "❌ Environment file not found: $EnvFilePath" -ForegroundColor Red
    Write-Host "Copy .env.example to .env and configure your settings" -ForegroundColor Yellow
    exit 1
}

Write-Host "Loading environment variables from: $EnvFile" -ForegroundColor Yellow

# Parse .env file
$EnvVars = @{}
Get-Content $EnvFilePath | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        # Remove quotes if present
        $value = $value -replace '^[''"]|[''"]$', ''
        if ($name -and $value -and -not $name.StartsWith('#')) {
            $EnvVars[$name] = $value
        }
    }
}

Write-Host "✅ Loaded $($EnvVars.Count) environment variables" -ForegroundColor Green

# Display loaded variables (mask sensitive values)
Write-Host ""
Write-Host "Variables to update:" -ForegroundColor Cyan
foreach ($key in $EnvVars.Keys | Sort-Object) {
    $value = $EnvVars[$key]
    if ($key -match 'KEY|SECRET|PASSWORD|TOKEN') {
        $maskedValue = $value.Substring(0, [Math]::Min(8, $value.Length)) + "..." + $value.Substring([Math]::Max(0, $value.Length - 4))
        Write-Host "  $key = $maskedValue" -ForegroundColor Gray
    } else {
        Write-Host "  $key = $value" -ForegroundColor White
    }
}

# Convert to JSON for AWS CLI
$EnvVarsJson = $EnvVars | ConvertTo-Json -Compress

Write-Host ""
Write-Host "Updating Lambda function: $FunctionName" -ForegroundColor Yellow

aws lambda update-function-configuration `
    --function-name $FunctionName `
    --environment "Variables=$EnvVarsJson" `
    --region $Region | Out-Null

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Environment variables updated successfully" -ForegroundColor Green
    
    # Wait for update to complete
    Write-Host "Waiting for Lambda to be ready..." -ForegroundColor Yellow
    $MaxAttempts = 30
    $Attempt = 0
    
    while ($Attempt -lt $MaxAttempts) {
        $Status = (aws lambda get-function --function-name $FunctionName --region $Region | ConvertFrom-Json).Configuration.State
        if ($Status -eq "Active") {
            Write-Host "✅ Lambda is ready" -ForegroundColor Green
            break
        }
        $Attempt++
        Start-Sleep -Seconds 2
    }
    
    if ($Attempt -eq $MaxAttempts) {
        Write-Host "⚠️  Lambda update is taking longer than expected" -ForegroundColor Yellow
        Write-Host "Check status: aws lambda get-function --function-name $FunctionName --region $Region" -ForegroundColor White
    }
} else {
    Write-Host "❌ Failed to update environment variables" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host "  ✅ Update Complete!" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host ""
Write-Host "Test your changes:" -ForegroundColor Cyan
Write-Host "  .\scripts\test-endpoint.ps1" -ForegroundColor White
Write-Host ""
