# Lambda Backend Architecture

## Executive Summary

Migration from **ECS Fargate** to **AWS Lambda + API Gateway** to achieve:
- **95% cost reduction** (~$30/month → ~$0.50/month)
- **Zero infrastructure maintenance**
- **Automatic scaling** from 0 to 1000s of concurrent requests
- **Pay-per-use pricing** (only charged for actual requests)

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                          Frontend                                │
│              (Next.js on Vercel)                                 │
│                                                                   │
│  https://your-app.vercel.app                                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    API Gateway (HTTP API)                        │
│                                                                   │
│  • Public HTTPS endpoint                                         │
│  • CORS configuration                                            │
│  • Request routing                                               │
│  • Rate limiting (optional)                                      │
│                                                                   │
│  https://xyz.execute-api.us-east-1.amazonaws.com                │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Lambda integration
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      AWS Lambda Function                         │
│                                                                   │
│  Function: llm-backend                                           │
│  Runtime: Python 3.13                                            │
│  Memory: 512 MB                                                  │
│  Timeout: 30 seconds                                             │
│  Concurrency: On-demand (up to 1000)                            │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │               FastAPI Application                         │  │
│  │                                                           │  │
│  │  ┌─────────────┐  ┌─────────────┐                       │  │
│  │  │   Health    │  │     AI      │                       │  │
│  │  │   Router    │  │   Router    │                       │  │
│  │  └─────────────┘  └─────────────┘                       │  │
│  │                          │                                │  │
│  │                          ▼                                │  │
│  │                  ┌─────────────┐                         │  │
│  │                  │  Bedrock    │                         │  │
│  │                  │  Service    │                         │  │
│  │                  └─────────────┘                         │  │
│  │                          │                                │  │
│  │                          ▼                                │  │
│  │                  ┌─────────────┐                         │  │
│  │                  │   JobLab    │                         │  │
│  │                  │    Tools    │                         │  │
│  │                  └─────────────┘                         │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  Mangum Adapter: Converts API Gateway events to ASGI            │
└────────┬───────────────────────────┬──────────────────────────┬─┘
         │                           │                          │
         │                           │                          │
         ▼                           ▼                          ▼
┌─────────────────┐     ┌────────────────────┐    ┌──────────────────┐
│  AWS Bedrock    │     │     Supabase      │    │  CloudWatch      │
│                 │     │                    │    │                  │
│  Claude 3.5     │     │  PostgreSQL DB     │    │  Logs + Metrics  │
│  Haiku          │     │  (via HTTP API)    │    │                  │
│                 │     │                    │    │  • Invocations   │
│  • Tool calling │     │  • Job listings    │    │  • Errors        │
│  • Streaming    │     │  • Analytics       │    │  • Duration      │
└─────────────────┘     └────────────────────┘    │  • Cold starts   │
                                                   └──────────────────┘
```

## Component Breakdown

### 1. API Gateway (HTTP API)
- **Type**: HTTP API (cheaper and faster than REST API)
- **URL**: Auto-generated (e.g., `https://abc123.execute-api.us-east-1.amazonaws.com`)
- **Features**:
  - Direct Lambda integration
  - CORS configuration
  - Automatic SSL/TLS
  - Request validation
  - Rate limiting (optional)
- **Cost**: $1.00 per million requests (first million free monthly)

### 2. Lambda Function
- **Name**: `llm-backend`
- **Runtime**: Python 3.13
- **Handler**: `lambda_handler.lambda_handler`
- **Configuration**:
  ```
  Memory: 512 MB
  Timeout: 30 seconds
  Environment: ~10 variables
  Package size: ~15 MB (with dependencies)
  ```
- **IAM Role**: `lambda-llm-backend-role`
  - Bedrock invoke permissions
  - CloudWatch logs permissions
- **Cost**: $0.20 per 1M requests (1GB-second pricing)

### 3. FastAPI + Mangum
- **Mangum**: ASGI adapter that translates API Gateway events to ASGI format
- **Process**:
  1. API Gateway receives HTTP request
  2. Sends event to Lambda
  3. Mangum converts event → ASGI
  4. FastAPI processes request
  5. Mangum converts response → API Gateway format
  6. API Gateway returns HTTP response

### 4. Dependencies
- Optimized for Lambda (removed uvicorn, testing libraries)
- Total dependencies:
  - fastapi
  - mangum
  - pydantic + pydantic-settings
  - boto3 (provided by Lambda runtime)
  - requests
  - python-dotenv

## Request Flow

### Typical Request Journey

```
1. Frontend sends POST /ai/ask
   └─> Body: {"prompt": "How many jobs in January 2026?"}

2. API Gateway receives request
   └─> Validates CORS
   └─> Routes to Lambda

3. Lambda invocation
   ├─> Cold start (if needed): 1-2 seconds
   │   └─> Load Python runtime
   │   └─> Import dependencies
   │   └─> Initialize FastAPI app
   │
   └─> Warm execution: ~100ms startup
       └─> Mangum processes event

4. FastAPI processes request
   └─> Route: /ai/ask
   └─> Validate request body
   └─> Call AI router

5. AI router logic
   └─> Detect database-related query
   └─> Call Bedrock with tool definitions
   └─> Bedrock returns tool_use (job_stats)
   └─> Execute tool against Supabase
   └─> Send results back to Bedrock
   └─> Bedrock returns natural language answer

6. Response journey
   └─> FastAPI formats response
   └─> Mangum converts to API Gateway format
   └─> API Gateway returns to frontend

Total time: 2-8 seconds (depending on Bedrock processing)
```

## Environment Variables

Lambda function environment:

```bash
# Application
APP_NAME=LLMBackend-Lambda
APP_VERSION=1.0.0
LOG_LEVEL=INFO

# AWS Services
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=us.anthropic.claude-3-5-haiku-20241022-v1:0
BEDROCK_MAX_TOKENS=1024
BEDROCK_TEMPERATURE=0.7

# External Services
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...

# CORS
CORS_ORIGINS=https://your-app.vercel.app,http://localhost:3000
```

## Security

### IAM Permissions (Principle of Least Privilege)

```json
{
  "Bedrock": [
    "bedrock:InvokeModel",
    "bedrock:InvokeModelWithResponseStream"
  ],
  "CloudWatch": [
    "logs:CreateLogGroup",
    "logs:CreateLogStream",
    "logs:PutLogEvents"
  ]
}
```

### Network Security
- **VPC**: Not required (Bedrock and Supabase are public services)
- **Secrets**: Stored in environment variables (consider AWS Secrets Manager for production)
- **CORS**: Configured on API Gateway to allow only specified origins
- **API Key**: Not implemented (can add via API Gateway if needed)

## Performance Characteristics

### Cold Start
- **Frequency**: After ~15 minutes of inactivity
- **Duration**: 1-2 seconds
- **Mitigation**: 
  - Use provisioned concurrency ($$$)
  - Accept cold starts for low-traffic apps
  - Frontend can show loading indicator

### Warm Execution
- **Startup**: ~50-100ms
- **Request processing**: 1-5 seconds (depends on Bedrock)
- **Total**: 1-6 seconds

### Concurrency
- **Default limit**: 1000 concurrent executions (per region)
- **Burst**: 500-3000 (region-dependent)
- **Reserved**: Can configure to prevent other Lambdas from stealing capacity

## Cost Comparison

### ECS Fargate (Previous)
```
1 Task (0.5 vCPU, 1 GB RAM):       $14.50/month
Application Load Balancer:         $16.20/month
Data transfer (10 GB):             $0.90/month
─────────────────────────────────────────────
Total:                             ~$31.60/month
```

### Lambda + API Gateway (New)
```
100,000 requests/month:
  Requests (after free tier):      $0.00
  Compute (2s avg, 512 MB):        $0.17
  API Gateway:                     $0.00 (free tier)
Data transfer (10 GB):             $0.90/month
─────────────────────────────────────────────
Total:                             ~$1.07/month

1 million requests/month:
  Requests:                        $0.20
  Compute:                         $1.67
  API Gateway:                     $1.00
Data transfer (100 GB):            $9.00/month
─────────────────────────────────────────────
Total:                             ~$11.87/month
```

**Savings**: 95%+ for low-traffic, 62%+ for high-traffic

## Monitoring & Observability

### CloudWatch Metrics (Automatic)
- Invocations
- Errors
- Duration (avg, min, max)
- Throttles
- Concurrent executions
- Cold start percentage

### CloudWatch Logs
- Log group: `/aws/lambda/llm-backend`
- Retention: 7 days (configurable)
- Structured logging from application

### Recommended Alarms
1. **Error rate > 5%**
2. **Duration > 25 seconds** (near timeout)
3. **Throttles > 0**
4. **Concurrent executions > 800** (approaching limit)

## Scaling Behavior

```
Traffic Pattern          Lambda Response
─────────────────────────────────────────────
0 requests/min          → 0 running instances (no cost)
10 requests/min         → 1-2 instances
100 requests/min        → 10-20 instances
1000 requests/min       → 100-200 instances
10000 requests/burst    → 500-1000 instances (burst limit)
```

Lambda automatically:
- Scales up based on request rate
- Reuses warm containers when possible
- Scales down to zero when idle
- No manual intervention required

## Limitations & Considerations

### Lambda Limits
| Limit | Value | Impact |
|-------|-------|--------|
| Max timeout | 15 minutes | 30s is sufficient for our use case |
| Max memory | 10 GB | 512 MB is sufficient |
| Max package size | 50 MB unzipped | Current: ~15 MB ✅ |
| Max concurrency | 1000 (default) | Can request increase |
| Max environment vars | 4 KB | Current: ~1 KB ✅ |

### Considerations
- **Cold starts**: Acceptable for low-traffic APIs
- **Statelessness**: No persistent connections (fine for HTTP/REST)
- **Execution time**: Must complete within timeout
- **No WebSockets**: Use API Gateway WebSocket API if needed

## Migration Checklist

- [x] Create lambda_backend folder structure
- [x] Copy and adapt FastAPI application
- [x] Create Mangum Lambda handler
- [x] Optimize requirements.txt
- [x] Create IAM policies
- [x] Create deployment scripts
- [x] Create testing scripts
- [ ] Deploy to AWS
- [ ] Test endpoints
- [ ] Update frontend configuration
- [ ] Monitor for 24 hours
- [ ] Optional: Delete ECS resources

## Rollback Plan

If issues arise:
1. Frontend: Switch endpoint back to ECS ALB
2. Backend: ECS service still running (unchanged)
3. Lambda: Can be deleted without affecting ECS

**Zero risk**: Old architecture remains untouched during migration.
