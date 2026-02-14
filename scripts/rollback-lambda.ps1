# =============================================================================
# Rollback Lambda Deployment
# Quickly rollback to a previous deployment package
# =============================================================================

param(
    [Parameter(Mandatory=$false)]
    [string]$PackageFile,
    
    [switch]$ListBackups
)

$ErrorActionPreference = "Stop"
$Region = "us-east-1"
$AccountId = "<AWS_ACCOUNT_ID>"
$FunctionName = "llm-backend"
$BucketName = "lambda-deployments-$AccountId"

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  Lambda Rollback Utility" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""

# Get script directory
$ScriptDir = Split-Path -Parent $PSCommandPath
$LambdaDir = Split-Path -Parent $ScriptDir

# List available backup packages
if ($ListBackups) {
    Write-Host "Checking for backup packages..." -ForegroundColor Yellow
    Write-Host ""
    
    # Check local backups
    Write-Host "Local backups (in lambda_backend/):" -ForegroundColor Cyan
    $LocalZips = Get-ChildItem $LambdaDir -Filter "*.zip" | Sort-Object LastWriteTime -Descending
    
    if ($LocalZips.Count -gt 0) {
        foreach ($zip in $LocalZips) {
            $SizeMB = [math]::Round($zip.Length / 1MB, 2)
            $Age = (Get-Date) - $zip.LastWriteTime
            
            if ($Age.TotalHours -lt 1) {
                $AgeStr = "$([math]::Round($Age.TotalMinutes, 0)) minutes ago"
            } elseif ($Age.TotalDays -lt 1) {
                $AgeStr = "$([math]::Round($Age.TotalHours, 1)) hours ago"
            } else {
                $AgeStr = "$([math]::Round($Age.TotalDays, 1)) days ago"
            }
            
            Write-Host "  • $($zip.Name)" -ForegroundColor White
            Write-Host "    Size: $SizeMB MB | Modified: $AgeStr" -ForegroundColor Gray
        }
    } else {
        Write-Host "  No local backup packages found" -ForegroundColor Gray
    }
    
    Write-Host ""
    
    # Check S3 backups
    Write-Host "S3 backups (in s3://$BucketName):" -ForegroundColor Cyan
    $S3Exists = aws s3 ls "s3://$BucketName/lambda-backend/" --region $Region 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        $S3Files = aws s3 ls "s3://$BucketName/lambda-backend/" --region $Region --recursive | 
                   Out-String | 
                   ForEach-Object { $_ -split "`n" } |
                   Where-Object { $_ -match "\.zip$" } |
                   Sort-Object -Descending
        
        if ($S3Files.Count -gt 0) {
            foreach ($line in $S3Files | Select-Object -First 10) {
                if ($line -match "(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\d+)\s+(.+)$") {
                    $Date = $matches[1]
                    $Size = [math]::Round([int]$matches[2] / 1MB, 2)
                    $Key = $matches[3]
                    $FileName = Split-Path $Key -Leaf
                    
                    Write-Host "  • $FileName" -ForegroundColor White
                    Write-Host "    Size: $Size MB | Uploaded: $Date" -ForegroundColor Gray
                }
            }
            
            if ($S3Files.Count -gt 10) {
                Write-Host "  ... and $($S3Files.Count - 10) more" -ForegroundColor Gray
            }
        } else {
            Write-Host "  No S3 backup packages found" -ForegroundColor Gray
        }
    } else {
        Write-Host "  S3 bucket not accessible or doesn't exist" -ForegroundColor Gray
    }
    
    Write-Host ""
    Write-Host "To rollback to a specific package:" -ForegroundColor Cyan
    Write-Host "  .\scripts\rollback-lambda.ps1 -PackageFile 'deployment-package.zip'" -ForegroundColor White
    Write-Host "  .\scripts\rollback-lambda.ps1 -PackageFile 's3://bucket/key/file.zip'" -ForegroundColor White
    Write-Host ""
    
    exit 0
}

# Rollback to specific package
if (-not $PackageFile) {
    Write-Host "❌ No package file specified" -ForegroundColor Red
    Write-Host ""
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  List backups:  .\scripts\rollback-lambda.ps1 -ListBackups" -ForegroundColor White
    Write-Host "  Rollback:      .\scripts\rollback-lambda.ps1 -PackageFile 'deployment-package.zip'" -ForegroundColor White
    Write-Host ""
    exit 1
}

Write-Host "Rollback target: $PackageFile" -ForegroundColor Yellow
Write-Host ""

# Check if S3 path
if ($PackageFile -like "s3://*") {
    # S3 rollback
    if ($PackageFile -match "s3://([^/]+)/(.+)") {
        $S3Bucket = $matches[1]
        $S3Key = $matches[2]
    } else {
        Write-Host "❌ Invalid S3 path format" -ForegroundColor Red
        Write-Host "   Expected: s3://bucket-name/path/to/file.zip" -ForegroundColor Yellow
        exit 1
    }
    
    Write-Host "Rolling back from S3..." -ForegroundColor Cyan
    Write-Host "  Bucket: $S3Bucket" -ForegroundColor Gray
    Write-Host "  Key: $S3Key" -ForegroundColor Gray
    Write-Host ""
    
    aws lambda update-function-code `
        --function-name $FunctionName `
        --s3-bucket $S3Bucket `
        --s3-key $S3Key `
        --region $Region `
        --output json | Out-Null
        
} else {
    # Local file rollback
    $LocalPath = Join-Path $LambdaDir $PackageFile
    
    if (-not (Test-Path $LocalPath)) {
        Write-Host "❌ Package file not found: $LocalPath" -ForegroundColor Red
        Write-Host "   Run with -ListBackups to see available packages" -ForegroundColor Yellow
        exit 1
    }
    
    $SizeMB = [math]::Round((Get-Item $LocalPath).Length / 1MB, 2)
    Write-Host "Rolling back from local file..." -ForegroundColor Cyan
    Write-Host "  File: $PackageFile" -ForegroundColor Gray
    Write-Host "  Size: $SizeMB MB" -ForegroundColor Gray
    Write-Host ""
    
    if ($SizeMB -gt 50) {
        Write-Host "⚠️  Package > 50MB, uploading to S3 first..." -ForegroundColor Yellow
        
        $S3Key = "lambda-backend/rollback-$(Get-Date -Format 'yyyyMMdd-HHmmss').zip"
        aws s3 cp $LocalPath "s3://$BucketName/$S3Key" --region $Region --quiet
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ Failed to upload to S3" -ForegroundColor Red
            exit 1
        }
        
        aws lambda update-function-code `
            --function-name $FunctionName `
            --s3-bucket $BucketName `
            --s3-key $S3Key `
            --region $Region `
            --output json | Out-Null
    } else {
        aws lambda update-function-code `
            --function-name $FunctionName `
            --zip-file "fileb://$LocalPath" `
            --region $Region `
            --output json | Out-Null
    }
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Rollback failed" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Rollback initiated" -ForegroundColor Green
Write-Host ""

# Wait for update to complete
Write-Host "Waiting for Lambda to update..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Test endpoint
Write-Host "Testing endpoint..." -ForegroundColor Yellow

$ApiName = "llm-backend-api"
$Apis = aws apigatewayv2 get-apis --region $Region | ConvertFrom-Json
$Api = $Apis.Items | Where-Object { $_.Name -eq $ApiName } | Select-Object -First 1

if ($Api) {
    $Endpoint = $Api.ApiEndpoint
    
    try {
        $Response = Invoke-RestMethod -Uri "$Endpoint/health" -Method Get -ErrorAction Stop
        
        if ($Response.status -eq "ok") {
            Write-Host "✅ Health check passed after rollback" -ForegroundColor Green
            Write-Host "   Status: $($Response.status)" -ForegroundColor Gray
            Write-Host "   Version: $($Response.version)" -ForegroundColor Gray
        } else {
            Write-Host "⚠️  Unexpected response: $($Response | ConvertTo-Json -Compress)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "❌ Health check failed: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "   Check logs: aws logs tail /aws/lambda/$FunctionName --follow" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host "  ✅ Rollback Complete" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  • Test thoroughly: .\scripts\test-endpoint.ps1" -ForegroundColor White
Write-Host "  • View logs: aws logs tail /aws/lambda/$FunctionName --follow" -ForegroundColor White
Write-Host "  • Fix issues, then redeploy: .\scripts\update-lambda.ps1" -ForegroundColor White
Write-Host ""
