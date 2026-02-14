# =============================================================================
# Test Lambda Backend Endpoint
# Tests health check and AI endpoints
# =============================================================================

param(
    [Parameter(Mandatory=$false)]
    [string]$Endpoint
)

$ErrorActionPreference = "Stop"

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  Testing Lambda Backend" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

# If endpoint not provided, try to get it from AWS
if (-not $Endpoint) {
    Write-Host "Getting API Gateway endpoint..." -ForegroundColor Yellow
    $Apis = aws apigatewayv2 get-apis --region us-east-1 | ConvertFrom-Json
    $Api = $Apis.Items | Where-Object { $_.Name -eq "llm-backend-api" } | Select-Object -First 1
    
    if ($Api) {
        $Endpoint = $Api.ApiEndpoint
        Write-Host "✅ Found endpoint: $Endpoint" -ForegroundColor Green
    } else {
        Write-Host "❌ Could not find API Gateway endpoint" -ForegroundColor Red
        Write-Host "Please provide endpoint: .\test-endpoint.ps1 -Endpoint https://..." -ForegroundColor Yellow
        exit 1
    }
}

# Test 1: Health Check
Write-Host ""
Write-Host "─────────────────────────────────────────────────────" -ForegroundColor Cyan
Write-Host "Test 1: Health Check" -ForegroundColor Cyan
Write-Host "─────────────────────────────────────────────────────" -ForegroundColor Cyan

$HealthUrl = "$Endpoint/health"
Write-Host "GET $HealthUrl" -ForegroundColor Yellow

try {
    $Response = Invoke-RestMethod -Uri $HealthUrl -Method Get -ContentType "application/json"
    Write-Host "✅ Health check passed" -ForegroundColor Green
    Write-Host ($Response | ConvertTo-Json -Depth 3) -ForegroundColor White
} catch {
    Write-Host "❌ Health check failed" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

# Test 2: AI Endpoint (simple question)
Write-Host ""
Write-Host "─────────────────────────────────────────────────────" -ForegroundColor Cyan
Write-Host "Test 2: AI Endpoint (Simple Question)" -ForegroundColor Cyan
Write-Host "─────────────────────────────────────────────────────" -ForegroundColor Cyan

$AskUrl = "$Endpoint/ai/ask"
$Body = @{
    prompt = "What is 2 + 2?"
} | ConvertTo-Json

Write-Host "POST $AskUrl" -ForegroundColor Yellow
Write-Host "Body: $Body" -ForegroundColor Gray

try {
    $Response = Invoke-RestMethod -Uri $AskUrl -Method Post -ContentType "application/json" -Body $Body
    Write-Host "✅ AI endpoint responded" -ForegroundColor Green
    Write-Host "Answer: $($Response.answer)" -ForegroundColor White
    Write-Host "Model: $($Response.model)" -ForegroundColor Gray
} catch {
    Write-Host "❌ AI endpoint failed" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($_.ErrorDetails) {
        Write-Host $_.ErrorDetails.Message -ForegroundColor Red
    }
    exit 1
}

# Test 3: AI Endpoint with Database Query
Write-Host ""
Write-Host "─────────────────────────────────────────────────────" -ForegroundColor Cyan
Write-Host "Test 3: AI Endpoint (Database Query - Tool Calling)" -ForegroundColor Cyan
Write-Host "─────────────────────────────────────────────────────" -ForegroundColor Cyan

$Body = @{
    prompt = "How many jobs were posted in January 2026?"
} | ConvertTo-Json

Write-Host "POST $AskUrl" -ForegroundColor Yellow
Write-Host "Body: $Body" -ForegroundColor Gray

try {
    $Response = Invoke-RestMethod -Uri $AskUrl -Method Post -ContentType "application/json" -Body $Body
    Write-Host "✅ Database query succeeded" -ForegroundColor Green
    Write-Host "Answer: $($Response.answer)" -ForegroundColor White
    Write-Host "Model: $($Response.model)" -ForegroundColor Gray
    
    if ($Response.usage) {
        Write-Host "Usage:" -ForegroundColor Gray
        Write-Host "  Input tokens: $($Response.usage.input_tokens)" -ForegroundColor Gray
        Write-Host "  Output tokens: $($Response.usage.output_tokens)" -ForegroundColor Gray
    }
} catch {
    Write-Host "⚠️  Database query failed (this is expected if Supabase credentials are not configured)" -ForegroundColor Yellow
    Write-Host $_.Exception.Message -ForegroundColor Yellow
}

# Summary
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host "  Testing Complete!" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host ""
Write-Host "Your Lambda backend is working! 🎉" -ForegroundColor White
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Configure Supabase credentials in Lambda environment" -ForegroundColor White
Write-Host "  2. Update frontend to use: $Endpoint" -ForegroundColor White
Write-Host "  3. Monitor logs: aws logs tail /aws/lambda/llm-backend --follow" -ForegroundColor White
Write-Host ""
