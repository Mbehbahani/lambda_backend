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
$ReservedLambdaKeys = @(
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
    "AWS_EXECUTION_ENV",
    "AWS_LAMBDA_FUNCTION_NAME",
    "AWS_LAMBDA_FUNCTION_MEMORY_SIZE",
    "AWS_LAMBDA_FUNCTION_VERSION",
    "AWS_LAMBDA_INITIALIZATION_TYPE",
    "AWS_LAMBDA_LOG_GROUP_NAME",
    "AWS_LAMBDA_LOG_STREAM_NAME",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "_HANDLER",
    "_X_AMZN_TRACE_ID",
    "LAMBDA_RUNTIME_DIR",
    "LAMBDA_TASK_ROOT",
    "TZ"
)
Get-Content $EnvFilePath | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        # Remove quotes if present
        $value = $value -replace '^[''"]|[''"]$', ''
        if ($ReservedLambdaKeys -contains $name) {
            Write-Host "Skipping reserved Lambda key: $name" -ForegroundColor Yellow
        }
        elseif ($name -and $value -and -not $name.StartsWith('#')) {
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

Write-Host ""
Write-Host "Updating Lambda function: $FunctionName" -ForegroundColor Yellow

# Build environment payload as JSON file to avoid CLI quoting/escaping issues.
$EnvPayload = @{
    Variables = $EnvVars
}
$EnvPayloadJson = $EnvPayload | ConvertTo-Json -Compress
$TempEnvFile = Join-Path $env:TEMP ("lambda-env-{0}.json" -f ([Guid]::NewGuid().ToString("N")))
[System.IO.File]::WriteAllText($TempEnvFile, $EnvPayloadJson, (New-Object System.Text.UTF8Encoding($false)))

try {
    aws lambda update-function-configuration `
        --function-name $FunctionName `
        --environment "file://$TempEnvFile" `
        --region $Region | Out-Null
}
finally {
    if (Test-Path $TempEnvFile) {
        Remove-Item $TempEnvFile -Force -ErrorAction SilentlyContinue
    }
}

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
