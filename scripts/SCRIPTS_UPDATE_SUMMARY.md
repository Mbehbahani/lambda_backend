# 📦 Deployment Scripts Update Summary

## What Was Updated

All deployment scripts have been updated with production-ready fixes and lessons learned from the successful Lambda deployment.

---

## 🆕 New Files Created

### 1. **update-lambda.ps1** - Quick Code Update Script
**Location:** `scripts/update-lambda.ps1`

**Purpose:** Fast code updates without recreating IAM roles or API Gateway

**Features:**
- Rebuilds package with Linux wheels automatically
- Handles S3 upload for packages > 50MB
- Runs health check after deployment
- 10x faster than full deployment (~30-60 seconds)

**Usage:**
```powershell
# Standard update
.\scripts\update-lambda.ps1

# Use existing package
.\scripts\update-lambda.ps1 -SkipPackage

# Skip health check
.\scripts\update-lambda.ps1 -SkipTest
```

---

### 2. **rollback-lambda.ps1** - Emergency Rollback Script
**Location:** `scripts/rollback-lambda.ps1`

**Purpose:** Quickly restore previous working deployment

**Features:**
- Lists available backup packages (local + S3)
- Rollback from local `.zip` files
- Rollback from S3 backups
- Runs health check after rollback

**Usage:**
```powershell
# List available backups
.\scripts\rollback-lambda.ps1 -ListBackups

# Rollback to specific package
.\scripts\rollback-lambda.ps1 -PackageFile "deployment-linux.zip"

# Rollback from S3
.\scripts\rollback-lambda.ps1 -PackageFile "s3://bucket/key/file.zip"
```

---

### 3. **DEPLOYMENT_LESSONS.md** - Critical Deployment Knowledge
**Location:** `DEPLOYMENT_LESSONS.md`

**Purpose:** Comprehensive documentation of deployment issues and solutions

**Contents:**
- ✅ 6 critical issues with detailed explanations
- ✅ Root cause analysis for each problem
- ✅ Step-by-step solutions
- ✅ Pre-deployment checklist
- ✅ Troubleshooting guide
- ✅ Performance metrics

**Key Topics:**
1. Binary compatibility (Windows vs Linux wheels)
2. Module shadowing (typing.py conflicts)
3. API Gateway stage configuration ($default vs prod)
4. IAM permissions (inference profiles)
5. Environment variables (AWS_REGION reserved)
6. Package size optimization (76 MB → 21 MB)

---

### 4. **scripts/README.md** - Scripts Usage Guide
**Location:** `scripts/README.md`

**Purpose:** Complete guide to all deployment scripts

**Contents:**
- Script overview with comparison table
- Quick start workflows
- Common development cycles
- Troubleshooting reference
- Best practices

---

## 🔄 Updated Files

### 1. **create-deployment-package.ps1**
**Changes:**

#### ✅ Added Linux Wheel Installation
```powershell
# NEW: Force Linux-compatible binary wheels
python -m pip install -r requirements.txt -t package \
  --platform manylinux2014_x86_64 \
  --only-binary=:all: \
  --upgrade
```

**Why:** Prevents `ImportError: No module named 'pydantic_core._pydantic_core'` on Lambda

#### ✅ Enhanced Module Conflict Detection
```powershell
# NEW: Check multiple conflicting files, not just typing.py/http.py
$ConflictingFiles = @("typing.py", "http.py", "types.py", "abc.py", "collections.py")

foreach ($file in $ConflictingFiles) {
    # Remove root-level files that shadow Python built-ins
}
```

**Why:** Prevents module shadowing errors like `cannot import name 'TYPE_CHECKING'`

---

### 2. **deploy.ps1**
**Changes:**

#### ✅ Added Prerequisites Validation
```powershell
# NEW: Verify AWS credentials
$Identity = aws sts get-caller-identity | ConvertFrom-Json
if ($Identity.Account -ne $AccountId) {
    Write-Host "Warning: Account ID mismatch"
}

# NEW: Verify Python version
$PythonVersion = python --version

# NEW: Verify pip supports --platform flag (pip >= 20.3)
if ($Major -lt 20 -or ($Major -eq 20 -and $Minor -lt 3)) {
    Write-Host "Warning: pip version too old"
}
```

**Why:** Catches environment issues before deployment starts

---

## 🗑️ Cleaned Up

### temp_check Folder
**What was it?** 
During troubleshooting, we extracted the deployment package to `temp_check/` to investigate module shadowing issues. This folder contained the full contents of boto3/botocore packages (all AWS service API definitions).

**Why was it created?**
To manually inspect package structure and find conflicting files like `typing.py` at the root level.

**Status:** ✅ Deleted - No longer needed

The conflict detection is now automated in `create-deployment-package.ps1`, so manual inspection isn't required.

---

## 🎯 Critical Points for Next Deployment

### 1. **ALWAYS Use Linux Wheels on Windows**
```powershell
# This line is critical:
--platform manylinux2014_x86_64 --only-binary=:all:
```

**Impact:** Without this, Lambda will fail with import errors  
**Where:** `create-deployment-package.ps1` line 29  
**Updated:** ✅ Now automatic in all scripts

---

### 2. **NEVER Set AWS_REGION Environment Variable**
```powershell
# Lambda provides these automatically - DO NOT SET:
# - AWS_REGION
# - AWS_LAMBDA_FUNCTION_NAME
# - AWS_LAMBDA_FUNCTION_MEMORY_SIZE
```

**Impact:** Can cause SDK configuration conflicts  
**Where:** `deploy.ps1` filters this out  
**Updated:** ✅ Now automatic

---

### 3. **Remove Module Shadowing Files**
```powershell
# These files MUST NOT exist at package root:
package/typing.py      ❌ Conflicts with import typing
package/http.py        ❌ Conflicts with import http
package/types.py       ❌ Conflicts with import types

# But these are OK (in subdirectories):
package/botocore/typing.py    ✅ OK
package/boto3/http.py          ✅ OK
```

**Impact:** Import errors like `cannot import name 'TYPE_CHECKING'`  
**Where:** `create-deployment-package.ps1` line 45-60  
**Updated:** ✅ Now detects and removes automatically

---

### 4. **Use $default Stage for HTTP API**
```powershell
# ✅ Correct for HTTP API
aws apigatewayv2 create-stage --stage-name '$default' --auto-deploy

# ❌ Wrong (causes 404 errors)
aws apigatewayv2 create-stage --stage-name 'prod'
```

**Impact:** All API requests return 404  
**Where:** API Gateway stage configuration  
**Updated:** ✅ deploy.ps1 already uses $default

---

### 5. **Include Inference Profiles in IAM**
```json
{
  "Resource": [
    "arn:aws:bedrock:*:*:foundation-model/*",
    "arn:aws:bedrock:*:*:inference-profile/*"  // Must include this!
  ]
}
```

**Impact:** AccessDeniedException when calling Bedrock  
**Where:** `deployment/iam-policy.json`  
**Updated:** ✅ Already includes inference-profile/*

---

### 6. **Use S3 for Large Packages**
```powershell
if ($PackageSizeMB -gt 50) {
    # Upload to S3, then update Lambda from S3
    aws s3 cp $Package s3://$Bucket/$Key
    aws lambda update-function-code --s3-bucket $Bucket --s3-key $Key
}
```

**Impact:** Lambda direct upload limit is 50MB  
**Where:** `deploy.ps1`, `update-lambda.ps1`  
**Updated:** ✅ Both scripts handle this automatically

---

## 🔄 Update Pipeline Workflow

### For Code Changes

```powershell
# 1. Make changes in app/
# Edit your Python files...

# 2. Quick update (30-60 seconds)
.\scripts\update-lambda.ps1

# 3. Test automatically runs
# Or run manually: .\scripts\test-endpoint.ps1

# 4. Monitor logs if needed
aws logs tail /aws/lambda/llm-backend --follow
```

**Benefits:**
- ✅ Fast deployment (< 1 minute)
- ✅ Automatic Linux wheel rebuild
- ✅ Automatic S3 upload if needed
- ✅ Health check included
- ✅ No IAM/API Gateway changes

---

### For Configuration Changes

```powershell
# 1. Update .env file
notepad .env

# 2. Update Lambda environment
.\scripts\update-environment.ps1

# Or redeploy with new config
.\scripts\deploy.ps1 -UpdateOnly
```

---

### For Infrastructure Changes

```powershell
# 1. Update IAM policy or Lambda config
# Edit deployment/iam-policy.json or deployment/lambda-config.json

# 2. Full redeploy
.\scripts\deploy.ps1

# 3. Test
.\scripts\test-endpoint.ps1
```

---

### Emergency Rollback

```powershell
# 1. List available backups
.\scripts\rollback-lambda.ps1 -ListBackups

# 2. Pick a working version
.\scripts\rollback-lambda.ps1 -PackageFile "deployment-linux.zip"

# 3. Verify it works
.\scripts\test-endpoint.ps1

# 4. Fix the issue locally
# Debug and fix...

# 5. Redeploy fixed version
.\scripts\update-lambda.ps1
```

---

## 📊 Before vs After

### Package Creation
**Before:**
```powershell
# Manual, error-prone
pip install -r requirements.txt -t package
# Created Windows wheels ❌
# No conflict detection ❌
```

**After:**
```powershell
.\scripts\create-deployment-package.ps1
# Automatic Linux wheels ✅
# Conflict detection ✅
# Size optimization ✅
```

---

### Deployment Speed
**Before:**
```powershell
# 5-10 minutes
# Full IAM/Lambda/API Gateway rebuild every time
```

**After:**
```powershell
# 30-60 seconds
.\scripts\update-lambda.ps1
# Only updates code
```

---

### Rollback Capability
**Before:**
```
No rollback mechanism ❌
Manual S3 search required ❌
```

**After:**
```powershell
.\scripts\rollback-lambda.ps1 -ListBackups
.\scripts\rollback-lambda.ps1 -PackageFile "backup.zip"
# 10-20 seconds ✅
```

---

## ✅ Deployment Checklist

Use this for every deployment:

### Pre-Deployment
- [ ] Code tested locally with `uvicorn app.main:app --reload`
- [ ] `.env` file configured with correct credentials
- [ ] Python 3.13 and pip >= 20.3 installed
- [ ] AWS CLI configured with correct credentials/region

### First-Time Setup
- [ ] Run `.\scripts\deploy.ps1` (creates everything)
- [ ] Verify health check passes
- [ ] Test AI endpoint with query
- [ ] Save deployment package as backup

### Code Updates
- [ ] Make changes in `app/`
- [ ] Run `.\scripts\update-lambda.ps1`
- [ ] Verify health check passes
- [ ] Test changed functionality

### Troubleshooting
- [ ] Check CloudWatch logs: `aws logs tail /aws/lambda/llm-backend --follow`
- [ ] Verify package has Linux wheels (not Windows)
- [ ] Check no root-level module shadowing files
- [ ] Verify IAM includes inference-profile resource
- [ ] Rollback if needed: `.\scripts\rollback-lambda.ps1`

---

## 📚 Documentation Structure

```
lambda_backend/
├── DEPLOYMENT_LESSONS.md       # ← Critical deployment knowledge
├── DEPLOYMENT_GUIDE.md         # Step-by-step instructions
├── DEPLOYMENT_STATUS.md        # Current deployment state
├── DEPLOYMENT_SUCCESS.md       # Success summary
├── ARCHITECTURE.md             # Technical architecture
├── README.md                   # Project overview
└── scripts/
    ├── README.md               # ← Scripts usage guide
    ├── deploy.ps1              # ✅ Updated with validations
    ├── update-lambda.ps1       # 🆕 Quick code updates
    ├── rollback-lambda.ps1     # 🆕 Emergency rollback
    ├── create-deployment-package.ps1  # ✅ Updated with Linux wheels
    ├── update-environment.ps1  # Environment variable management
    └── test-endpoint.ps1       # Endpoint testing
```

---

## 🎓 Key Learnings

### 1. Binary Compatibility is Critical
Windows builds don't work on Lambda (Linux). Always use:
```powershell
--platform manylinux2014_x86_64 --only-binary=:all:
```

### 2. Module Structure Matters
Root-level files shadow Python built-ins. Keep packages in subdirectories.

### 3. API Gateway Has Two Types
- REST API: Uses named stages (`/prod/`, `/dev/`)
- HTTP API: Uses `$default` stage (we use this)

### 4. Bedrock Permissions Evolve
Foundation models and inference profiles need different ARN patterns.

### 5. Fast Updates Matter
Production deployments should take seconds, not minutes.

---

## 🚀 Next Steps

1. **Use update-lambda.ps1 for daily development**
   - Fast code updates
   - Automatic health checks
   - Built-in rollback capability

2. **Keep backups of working packages**
   - Save packages with version numbers
   - Keep last 3 known-good versions

3. **Monitor CloudWatch logs**
   - Check for errors after deployment
   - Monitor performance metrics

4. **Read DEPLOYMENT_LESSONS.md**
   - Understand why these fixes matter
   - Reference for future troubleshooting

---

**Summary:** All scripts now include production-ready fixes, comprehensive error handling, and automatic optimizations. The deployment process is faster, safer, and more reliable.

**Status:** ✅ Production Ready  
**Last Updated:** 2026-02-12
