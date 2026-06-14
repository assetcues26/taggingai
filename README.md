
Final 4.o Code

# Azure Function: AI-Powered Asset Analysis (v6-ai-validation-dev)

## Table of Contents
1. [Project Overview](#project-overview)
2. [Architecture & Logic](#architecture--logic)
3. [Prerequisites](#prerequisites)
4. [Quick Deploy & Test](#quick-deploy--test)
5. [Configuration](#configuration)
6. [Deployment Commands](#deployment-commands)
7. [Testing & Validation](#testing--validation)
8. [Cache Management](#cache-management)
9. [Cost Protection](#cost-protection)
10. [Troubleshooting](#troubleshooting)
11. [File Structure](#file-structure)
12. [API Reference](#api-reference)

---

## Project Overview

This Azure Function provides intelligent asset analysis by combining:
- **Gemini AI**: Vision analysis, validation, and recommendations
- **Multipart image uploads**: Direct file upload (no base64 JSON)
- **Cost Protection**: Multiple layers of API cost controls

### Key Features
- Anonymous access (no authentication required for testing)
- Comprehensive cost protection (rate limits, token limits, circuit breakers)
- Image processing with automatic resizing
- Phase 1 vision, Phase 1.5 name/description match, Phase 2 subcategory/model validation

### Current Deployment
- **Resource Group**: v6-AI
- **Function App**: v6-ai-validation-dev
- **Runtime**: Python 3.12 on Linux Consumption Plan
- **Location**: East US

---

## Architecture & Logic

### Request Flow
```
POST multipart/form-data -> Parse images + metadata -> Gemini Phase 1 (vision)
-> Post-process (tag, cost, date) -> Gemini Phase 1.5 (name/description)
-> Gemini Phase 2 (subcategory/make-model) -> JSON response
```

No database is used. All analysis is performed in-memory via Gemini API calls per request.
1. **Rate Limiting**: In-memory limits per function instance
2. **Token Limits**: Capped per Gemini call
3. **Circuit Breaker**: Stops after consecutive failures
4. **Prompt Length**: Max 20000 characters input
5. **Retry Control**: Maximum 2 retries per call

---

## Prerequisites

### Required Software
```bash
# 1. Azure CLI
winget install Microsoft.AzureCLI

## Deploy & Test (Quick)

Below are the minimal PowerShell commands to create the Function App (if missing), set the GEMINI_API_KEY securely, and publish from this workspace. These assume you're signed in to `az` and have `func` installed.

```powershell
# 1. Ensure Azure CLI is logged in
az login
az account show # Verify subscription

# 2. Run the automated deploy script (creates resources if needed and publishes)
.\deploy.ps1

# 3. Set secrets securely (replace YOUR_KEY with actual key)
az functionapp config appsettings set --name v6-ai-validation-dev --resource-group v6-AI --settings "GEMINI_API_KEY=YOUR_KEY"

# 4. Test the deployed function
python smoke_test.py

# 5. To test locally (optional)
# Create virtual environment and install dependencies first:
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Copy local.settings.json.sample to local.settings.json and add your GEMINI_API_KEY
func start
```

# 2. Azure Functions Core Tools
npm install -g azure-functions-core-tools@4

# 3. Python 3.11 (for local development)
# Download from python.org

# 4. Git (for version control - optional)
winget install Git.Git
```

### Required Accounts & Keys
- **Azure Account** with active subscription (for Azure Functions deploy only)
- **Gemini API Key** from Google AI Studio (https://makersuite.google.com/app/apikey)

---

## Initial Setup

### 1. Download/Clone Project
```powershell
# Navigate to this workspace folder
cd "C:\Users\Assetrack\Desktop\SingleCallCodeGemini - AzureDeploy"
```

### 2. Install Dependencies (for local testing)
```powershell
# Create virtual environment (recommended for local development)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 3. Azure CLI Authentication
```powershell
# Login to Azure
az login

# Verify account and subscription
az account show

# List available subscriptions (if needed)
az account list --output table
```

---

## Configuration

### Environment Variables Setup

#### Gemini API Key (Required)
- Get your API key from: https://makersuite.google.com/app/apikey
- This will be set in Azure App Settings (never commit to source control)

### Local Settings (for local development only)
- Copy `local.settings.json.sample` to `local.settings.json`
- Add your GEMINI_API_KEY to the copied file for local testing
- The `.gitignore` prevents this file from being committed

---

## Deployment Commands

### Automated Deployment (Recommended)

#### 1. Run the Deploy Script
```powershell
# This script creates resource group, storage, Function App (if needed) and publishes
.\deploy.ps1
```

#### 2. Set Environment Variables (Required)
```powershell
# Set your Gemini API key
az functionapp config appsettings set --name v6-ai-validation-dev --resource-group v6-AI --settings `
 "GEMINI_API_KEY=your_actual_api_key_here" `
 "GEMINI_MODEL_NAME=gemini-3.1-flash-lite"
```

### Manual Deployment (Step by Step)

#### 1. Create Resource Group (if needed)
```powershell
az group create --name v6-AI --location "East US"
```

#### 2. Create Function App (if needed)
```powershell
$storageAccount = "v6aideploystorage$(Get-Random)"
az storage account create --name $storageAccount --location "East US" --resource-group v6-AI --sku Standard_LRS
az functionapp create --resource-group v6-AI --consumption-plan-location "East US" --runtime python --runtime-version 3.12 --functions-version 4 --name v6-ai-validation-dev --storage-account $storageAccount --os-type Linux
```

#### 3. Deploy Function Code
```powershell
func azure functionapp publish v6-ai-validation-dev
```

### Quick Deployment (Code Updates Only)

#### For Existing Function App
```powershell
func azure functionapp publish v6-ai-validation-dev
```

#### Update Specific Settings
```powershell
# Update Gemini API Key
az functionapp config appsettings set --name v6-ai-validation-dev --resource-group v6-AI --settings "GEMINI_API_KEY=new_api_key_here"
```

### Enable/Disable Authentication
```bash
# For testing (anonymous access)
# Edit function_app.py: auth_level=func.AuthLevel.ANONYMOUS
# Edit function.json: "authLevel": "anonymous"

# For production (function key required)
# Edit function_app.py: auth_level=func.AuthLevel.FUNCTION
# Edit function.json: "authLevel": "function"

# Then redeploy
func azure functionapp publish masterdata-func-354302549
```

---

## Testing & Validation

### Get Function URL & Keys
```powershell
# Get function app details
az functionapp show --name v6-ai-validation-dev --resource-group v6-AI --query "defaultHostName"

# Get function keys (if authentication enabled)
az functionapp keys list --name v6-ai-validation-dev --resource-group v6-AI
```

### Test Endpoints

#### Anonymous Testing (No Auth)
```powershell
$uri = "https://v6-ai-validation-dev-dabmevavh6aefuah.centralindia-01.azurewebsites.net/api/asset_analysis"
```

#### Automated Testing
```powershell
# Use the included smoke test script
python smoke_test.py
```

> **Note:** `smoke_test.py` is listed in `.funcignore`, so it isn't packaged when you run `func azure functionapp publish`. Keep local-only utilities in that file if you add more.

### Sample Test Requests

#### Basic Test (PowerShell)
```powershell
$body = @{
 assetid = "TEST123"
 tagnumber = "TAG001"
 assetnumber = "AN-TEST-001"
 assetclassid = 101
 assetname = "Samsung Split AC"
 description = "Demo payload for smoke test"
 company = "Samsung"
 assetclassname = "Air Conditioner"
 categoryname = "Electronics"
 subcategoryname = "Cooling"
 makemodelname = "Samsung WindFree"
 assetimage = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
 barcodeimage = $null
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri $uri -Method POST -Body $body -ContentType "application/json"
```

#### Cache Hit Testing
```powershell
# First call - fresh analysis
$result1 = Invoke-RestMethod -Uri $uri -Method POST -Body $body -ContentType "application/json"
Write-Host "First call error field:" $result1.error

# Second call - should cache hit
$result2 = Invoke-RestMethod -Uri $uri -Method POST -Body $body -ContentType "application/json"
Write-Host "Second call error field:" $result2.error
# Should show: "CACHE_HIT: assetid=TEST123, tagnumber=TAG001"
```

#### Postman Collection
```json
{
 "info": { "name": "Asset Analysis API" },
 "item": [
 {
 "name": "Asset Analysis",
 "request": {
 "method": "POST",
 "header": [
 { "key": "Content-Type", "value": "application/json" }
 ],
 "url": "https://masterdata-func-354302549.azurewebsites.net/api/asset_analysis",
 "body": {
 "raw": "{\n \"assetid\": \"12345\",\n \"tagnumber\": \"TAG001\",\n \"assetnumber\": \"AN-12345\",\n \"assetclassid\": 500,\n \"assetname\": \"Samsung Refrigerator\",\n \"description\": \"Stainless steel double door freezer\",\n \"company\": \"Samsung\",\n \"assetclassname\": \"Appliance\",\n \"categoryname\": \"Electronics\",\n \"assetimage\": \"base64_encoded_image\",\n \"barcodeimage\": null\n}"
 }
 }
 }
 ]
}
```

---

## Cache Management

### Cache Configuration
```python
# In function_app.py
asset_analysis_cache = {
 'results': {}, # "assetid|tagnumber" -> analysis_result
 'access_order': [], # LRU tracking
 'max_size': 50 # Maximum cached results
}
```

### Cache Key Logic
- **Cache Key**: `f"{assetid}|{tagnumber or ''}"`
- **Examples**:
 - assetid="123", tagnumber="TAG1" -> Key: "123|TAG1"
 - assetid="123", tagnumber=null -> Key: "123|"
 - assetid="456", tagnumber="TAG1" -> Key: "456|TAG1"

### Cache Hit Indicators
```json
{
 "error": "CACHE_HIT: assetid=123, tagnumber=TAG1",
 "message": "Result retrieved from cache - no new analysis performed",
 "...": "rest of cached data"
}
```

### Clear Cache (If Needed)
```powershell
# Restart function app to clear in-memory cache
az functionapp restart --name v6-ai-validation-dev --resource-group v6-AI
```

---

## Cost Protection

### Rate Limits (Configured)
```python
API_LIMITS = {
 'MAX_CALLS_PER_MINUTE': 150, # $7.50/min max
 'MAX_CALLS_PER_HOUR': 500, # $25.00/hour max
 'MAX_CALLS_PER_DAY': 5000, # $250.00/day max
 'MAX_RETRIES': 2, # Prevent retry storms
 'CIRCUIT_BREAKER_THRESHOLD': 10 # Stop after failures
}
```

### Token Limits (All API Calls Protected)
```python
# Output token limits by call type:
- General recommendations: max_tokens=150
- Name matching: max_tokens=100
- Validation: max_tokens=100
- Default fallback: max_tokens=200

# Input prompt limit: 8000 characters (~2000 tokens)
```

### Monitor Costs
```powershell
# Check API usage in logs
az functionapp log tail --name v6-ai-validation-dev --resource-group v6-AI

# Look for these log messages:
# "API USAGE ALERT: X calls today, Y this hour"
# "COST PROTECTION ACTIVATED"
# "DAILY/HOURLY API LIMIT EXCEEDED"
```

### Emergency Cost Controls
```powershell
# Stop function app immediately
az functionapp stop --name v6-ai-validation-dev --resource-group v6-AI

# Disable function app
az functionapp config appsettings set --name v6-ai-validation-dev --resource-group v6-AI --settings "AzureWebJobsDisableHomepage=true"
```

---

## Troubleshooting

### Common Issues & Solutions

#### 1. Deployment Fails
```bash
# Check Azure CLI login
az account show

# Verify resource group exists
az group list --query "[?name=='rg-masterdata-function']"

# Check function app status
az functionapp show --name masterdata-func-354302549 --resource-group rg-masterdata-function --query "state"
```

#### 2. Gemini API Errors
```bash
# Verify API key is set
az functionapp config appsettings list --name masterdata-func-354302549 --resource-group rg-masterdata-function --query "[?name=='GEMINI_API_KEY']"

# Check API limits in logs
az functionapp log tail --name masterdata-func-354302549 --resource-group rg-masterdata-function
```

#### 3. Function Not Responding
```bash
# Restart function app
az functionapp restart --name masterdata-func-354302549 --resource-group rg-masterdata-function

# Check function app logs
az functionapp log tail --name masterdata-func-354302549 --resource-group rg-masterdata-function
```

### Log Analysis Commands
```powershell
# Real-time logs
az functionapp log tail --name v6-ai-validation-dev --resource-group v6-AI

# Download logs
az functionapp log download --name v6-ai-validation-dev --resource-group v6-AI

# Check Application Insights (if configured)
# Go to Azure Portal -> Function App -> Application Insights
```

---

## File Structure

```
SingleValidation-POC-Enhance/
|-- function_app.py          # Main function code
|-- host.json                # Function app host settings
|-- requirements.txt         # Python dependencies (runtime + dev tools)
|-- pyproject.toml           # Ruff and pytest configuration
|-- prompts/                 # Prompt templates and builders
|   `-- templates/
|-- tests/                   # Unit tests
|-- local.settings.json      # Local secrets (not committed)
|-- .gitignore
|-- .funcignore
|-- README.md
`-- .vscode/                 # VS Code settings (optional)
```

### Key Files Explained

#### `function_app.py` (Main Logic)
- HTTP handler and orchestration for Phase 1, 1.5, and 2
- Gemini API integration with retry logic and cost protection
- Image processing, tag matching, cost/date validation

#### `requirements.txt` (Dependencies)
```
azure-functions==1.18.0 # Azure Functions framework
pillow==10.4.0 # Image processing
google-generativeai==0.3.2 # Gemini AI API
```

#### `function.json` (Function Configuration)
```json
{
 "scriptFile": "function_app.py",
 "bindings": [
 {
 "authLevel": "anonymous", # Change to "function" for auth
 "type": "httpTrigger",
 "direction": "in",
 "name": "req",
 "methods": ["post"]
 },
 {
 "type": "http",
 "direction": "out",
 "name": "$return"
 }
 ]
}
```

#### `host.json` (Host Settings)
```json
{
 "version": "2.0",
 "extensions": {
 "http": {
 "maxConcurrentRequests": 5, # Limit concurrent requests
 "maxOutstandingRequests": 50, # Queue limit
 "dynamicThrottlesEnabled": true # Auto-scaling protection
 }
 }
}
```

---

## API Reference

### Endpoint
```
POST https://v6-ai-validation-dev-dabmevavh6aefuah.centralindia-01.azurewebsites.net/api/asset_analysis
```

### Request Headers
```
Content-Type: application/json
```

### Request Body Schema
```json
{
 "assetid": "string", // Required for caching
 "tagnumber": "string", // Optional, part of cache key
 "assetnumber": "string", // New passthrough identifier (echoed in response)
 "assetclassid": 0, // New passthrough integer (echoed in response)
 "assetname": "string", // Human-provided asset name/label
 "description": "string", // Optional asset description
 "assetclassname": "string", // Asset type/class
 "categoryid": "string", // Optional category id
 "categoryname": "string", // Asset category
 "subcategoryid": "string", // Optional subcategory id
 "subcategoryname": "string", // Optional subcategory name
 "makemodelid": "string", // Optional make/model id
 "makemodelname": "string", // Optional make/model name
 "companyid": "string", // Optional company id
 "company": "string", // Asset company/brand
 "assetimage": "string", // Base64 encoded asset image
 "barcodeimage": "string" // Optional base64 barcode image
}
```

### Response Schema
```json
{
 "assetid": "string",
 "tagnumber": "string",
 "assetnumber": "string",
 "assetclassid": 0,
 "assetclassname": "string",
 "categoryname": "string",
 "subcategoryname": "string",
 "makemodelname": "string",
 "company": "string",
 "namedescriptionmatch": "Y/N",
 "namedescriptionmatchpercent": 0-100,
 "subcatmodelmatch": "Y/N",
 "subcatmodelmatchpercent": 0-100,
 "recommendedsubcategory": "string",
 "recommendedmakemodel": "string",
 "detectedtagnumber": "string",
 "detectedtagnumbermatch": "Y/N",
 "detectedtagnumbermatchpercent": 0-100,
 "imageReadability": "Y/N",
 "barcodeposition": {
 "position": "string | null"
 },
 "damage_assessment": "string",
 "error": "string", // Cache hit indicator or error
 "message": "string" // Additional information
}
```

### Cache Hit Response
```json
{
 "error": "CACHE_HIT: assetid=123, tagnumber=TAG001",
 "message": "Result retrieved from cache - no new analysis performed",
 "...": "cached analysis results"
}
```

### Error Responses
```json
// Rate limit exceeded
{
 "error": "DAILY API LIMIT EXCEEDED (5000 calls) - COST PROTECTION ACTIVATED"
}

// Invalid request
{
 "error": "Invalid JSON format in request body."
}

// API failure
{
 "error": "API_FAILURE",
 "message": "Gemini API error: details"
}
```

---

## Quick Start Checklist

### For New Setup:
- [ ] Install Azure CLI, Functions Core Tools
- [ ] Login to Azure: `az login`
- [ ] Get Gemini API key from Google AI Studio
- [ ] Create resource group: `az group create...`
- [ ] Create storage account: `az storage account create...`
- [ ] Create function app: `az functionapp create...`
- [ ] Configure environment variables: `az functionapp config appsettings set...`
- [ ] Deploy function: `func azure functionapp publish...`
- [ ] Test with sample request

### For Code Updates:
- [ ] Make changes to `function_app.py`
- [ ] Test locally if needed: `func start`
- [ ] Deploy updates: `func azure functionapp publish masterdata-func-354302549`
- [ ] Validate with test request
- [ ] Monitor logs for errors

### For Production:
- [ ] Enable authentication (`authLevel: "function"`)
- [ ] Set up monitoring/alerts in Azure Portal
- [ ] Configure backup/disaster recovery
- [ ] Document API keys and credentials securely
- [ ] Set up CI/CD pipeline (optional)

---

## Support & Maintenance

### Regular Maintenance Tasks
```powershell
# Monthly: Check API usage and costs
az functionapp log tail --name v6-ai-validation-dev --resource-group v6-AI | Select-String "API USAGE"

# Weekly: Restart function app to clear cache and refresh connections
az functionapp restart --name v6-ai-validation-dev --resource-group v6-AI

# As needed: Update Gemini API key
az functionapp config appsettings set --name v6-ai-validation-dev --resource-group v6-AI --settings "GEMINI_API_KEY=new_key"
```

### Monitoring & Alerts
- **Azure Portal**: Monitor function executions, errors, performance
- **Application Insights**: Detailed telemetry and performance metrics
- **Cost Management**: Track Gemini API costs and Azure Function costs
- **Log Analytics**: Search and analyze function logs

---

## License & Notes

**AI Provider**: Google Gemini API
**Cloud Platform**: Microsoft Azure Functions / Vercel
**Runtime**: Python 3.10+ (local), Python on Linux Consumption Plan (Azure)

**Last Updated**: October 1, 2025
**Function App**: v6-ai-validation-dev
**Resource Group**: v6-AI

---

*This Prd README provides complete instructions for deploying, managing, and troubleshooting the Asset Analysis Azure Function for Flipkart which requires no Subcategory and Model Analysis. Keep this document updated as the system evolves...*



