# =============================================================================
# Quick Lambda Update Script
# Use this for fast code updates after initial deployment
# =============================================================================

param(
    [switch]$SkipPackage,
    [switch]$SkipTest,
    [string]$PackageFile = "deployment-package.zip"
)

$ErrorActionPreference = "Stop"
$Region = "us-east-1"
$AccountId = "<AWS_ACCOUNT_ID>"
$FunctionName = "llm-backend"

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  Quick Lambda Code Update" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""

# Get script directory
$ScriptDir = Split-Path -Parent $PSCommandPath
$LambdaDir = Split-Path -Parent $ScriptDir

# Step 1: Create deployment package (if needed)
if (-not $SkipPackage) {
    Write-Host "─────────────────────────────────────────────────────" -ForegroundColor Cyan
    Write-Host "Step 1/3: Creating Deployment Package" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────────────────" -ForegroundColor Cyan
    
    & (Join-Path $ScriptDir "create-deployment-package.ps1") -OutputFile $PackageFile
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to create deployment package" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "⏭️  Skipping package creation" -ForegroundColor Yellow
}

$DeploymentPackage = Join-Path $LambdaDir $PackageFile

# Validate package exists
if (-not (Test-Path $DeploymentPackage)) {
    Write-Host "❌ Deployment package not found: $DeploymentPackage" -ForegroundColor Red
    Write-Host "   Run without -SkipPackage to create it" -ForegroundColor Yellow
    exit 1
}

# Check package size
$PackageSize = (Get-Item $DeploymentPackage).Length
$PackageSizeMB = [math]::Round($PackageSize / 1MB, 2)

Write-Host ""
Write-Host "─────────────────────────────────────────────────────" -ForegroundColor Cyan
Write-Host "Step 2/3: Uploading Code to Lambda" -ForegroundColor Cyan
Write-Host "─────────────────────────────────────────────────────" -ForegroundColor Cyan
Write-Host "Package size: $PackageSizeMB MB" -ForegroundColor Gray
Write-Host ""

if ($PackageSizeMB -gt 50) {
    # Use S3 for large packages
    Write-Host "Package exceeds 50MB limit, uploading via S3..." -ForegroundColor Yellow
    
    $BucketName = "lambda-deployments-$AccountId"
    $S3Key = "lambda-backend/deployment-$(Get-Date -Format 'yyyyMMdd-HHmmss').zip"
    
    # Upload to S3
    Write-Host "Uploading to S3: s3://$BucketName/$S3Key" -ForegroundColor Gray
    aws s3 cp $DeploymentPackage "s3://$BucketName/$S3Key" --region $Region --quiet
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to upload to S3" -ForegroundColor Red
        Write-Host "   Ensure bucket exists: aws s3 mb s3://$BucketName --region $Region" -ForegroundColor Yellow
        exit 1
    }
    
    Write-Host "✅ Uploaded to S3" -ForegroundColor Green
    
    # Update Lambda from S3
    Write-Host "Updating Lambda function from S3..." -ForegroundColor Yellow
    aws lambda update-function-code `
        --function-name $FunctionName `
        --s3-bucket $BucketName `
        --s3-key $S3Key `
        --region $Region `
        --output json | Out-Null
    
} else {
    # Direct upload for smaller packages
    Write-Host "Uploading directly to Lambda..." -ForegroundColor Yellow
    aws lambda update-function-code `
        --function-name $FunctionName `
        --zip-file "fileb://$DeploymentPackage" `
        --region $Region `
        --output json | Out-Null
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to update Lambda function code" -ForegroundColor Red
    Write-Host "   Check if function exists: aws lambda get-function --function-name $FunctionName --region $Region" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Lambda function code updated" -ForegroundColor Green

# Wait for update to complete
Write-Host ""
Write-Host "Waiting for update to complete..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

# Check function state
$FunctionState = aws lambda get-function --function-name $FunctionName --region $Region | ConvertFrom-Json
$State = $FunctionState.Configuration.State

if ($State -eq "Active") {
    Write-Host "✅ Function is active and ready" -ForegroundColor Green
} else {
    Write-Host "⚠️  Function state: $State" -ForegroundColor Yellow
    Write-Host "   Waiting for activation..." -ForegroundColor Gray
    Start-Sleep -Seconds 5
}

# Step 3: Test endpoint (optional)
if (-not $SkipTest) {
    Write-Host ""
    Write-Host "─────────────────────────────────────────────────────" -ForegroundColor Cyan
    Write-Host "Step 3/3: Testing Endpoint" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────────────────" -ForegroundColor Cyan
    
    # Get API Gateway endpoint
    $ApiName = "llm-backend-api"
    $Apis = aws apigatewayv2 get-apis --region $Region | ConvertFrom-Json
    $Api = $Apis.Items | Where-Object { $_.Name -eq $ApiName } | Select-Object -First 1
    
    if ($Api) {
        $Endpoint = $Api.ApiEndpoint
        Write-Host "Endpoint: $Endpoint" -ForegroundColor Gray
        Write-Host ""
        
        # Quick health check
        Write-Host "Testing /health endpoint..." -ForegroundColor Yellow
        try {
            $Response = Invoke-RestMethod -Uri "$Endpoint/health" -Method Get -ErrorAction Stop
            if ($Response.status -eq "ok") {
                Write-Host "✅ Health check passed" -ForegroundColor Green
                Write-Host "   Status: $($Response.status)" -ForegroundColor Gray
                Write-Host "   Version: $($Response.version)" -ForegroundColor Gray
            } else {
                Write-Host "⚠️  Unexpected response: $($Response | ConvertTo-Json -Compress)" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "❌ Health check failed: $($_.Exception.Message)" -ForegroundColor Red
            Write-Host "   Check CloudWatch logs for details" -ForegroundColor Yellow
        }
    } else {
        Write-Host "⚠️  API Gateway not found, skipping test" -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "⏭️  Skipping endpoint test" -ForegroundColor Yellow
}

# Summary
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host "  ✅ Lambda Update Complete!" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  • Test your changes: .\scripts\test-endpoint.ps1" -ForegroundColor White
Write-Host "  • View logs: aws logs tail /aws/lambda/$FunctionName --follow" -ForegroundColor White
Write-Host "  • Rollback if needed: Deploy previous package.zip" -ForegroundColor White
Write-Host ""
