# Cost Efficiency Score by Tag

Calculate the AWS Cost Optimization Hub Cost Efficiency Score grouped by a specific tag key (e.g., Application, Team, Environment). This fills a gap in the native Cost Optimization Hub console, which only supports efficiency scores at the account and region level.

## How It Works

The Cost Efficiency Score formula (same as the AWS Console):

```
Cost Efficiency = [1 - (Potential Savings / Total Optimizable Spend)] x 100%
```

This tool computes it per tag value by combining two AWS APIs:

1. **Potential Savings** — Uses `ListRecommendationSummaries` with `groupBy=TagKey:<key>` to get deduped savings per tag value in a single call.
2. **Total Optimizable Spend** — Uses the higher of:
   - Cost Explorer's 30-day net amortized spend (credits and refunds removed) for supported services (captures all resources, including those with no recommendations)
   - Sum of COH's `estimatedMonthlyCost` for recommended resources (730-hour normalized monthly cost)

   Using the higher value ensures the denominator stays consistent with the savings numerator, avoiding edge cases where calendar-day spend is slightly lower than COH's normalized monthly cost (e.g., partial days, variable month lengths).

The default time window is a **rolling 30 days**, matching the AWS Console behavior.

## Project Structure

```
COH Efficiency Score/
├── calculate_efficiency_by_tag.py    # Core logic + CLI tool
├── requirements.txt                  # Python dependencies for CLI
├── start.sh                          # Starts both API + UI servers
├── api/
│   ├── main.py                       # FastAPI backend
│   └── requirements.txt              # Python dependencies for API
└── ui/
    ├── package.json                  # Vite + Cloudscape React app
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx
        └── components/
            ├── FilterPanel.jsx       # Tag key/value input form
            ├── EfficiencySummary.jsx  # KPI cards + efficiency score table
            └── ResourceDetails.jsx   # Expandable per-tag resource tables
```

## Prerequisites

- Python 3.9+
- Node.js 18+
- AWS credentials configured with read access to:
  - Cost Optimization Hub (`cost-optimization-hub:ListRecommendations`, `cost-optimization-hub:ListRecommendationSummaries`)
  - Cost Explorer (`ce:GetCostAndUsage`)
- Cost Optimization Hub must be enabled in the account/organization
- Cost allocation tags must be activated in the Billing console

## Quick Start (Web UI)

The web UI uses the [AWS Cloudscape Design System](https://cloudscape.design/) so it looks and feels like the AWS Console.

```bash
# Install dependencies
pip3 install fastapi uvicorn boto3
cd ui && npm install && cd ..

# Start both servers
./start.sh
```

This launches:
- **UI**: http://localhost:3000
- **API**: http://localhost:8000
- **API Docs (Swagger)**: http://localhost:8000/docs

Press **Ctrl+C** to stop both servers.

## CLI Usage

```bash
pip3 install boto3

# Calculate cost efficiency for all values of the "Application" tag
python3 calculate_efficiency_by_tag.py --tag-key Application

# Calculate for a specific tag value
python3 calculate_efficiency_by_tag.py --tag-key Application --tag-value MyApp

# Include detailed resource list with recommendations
python3 calculate_efficiency_by_tag.py --tag-key Application --show-resources

# Output as JSON for programmatic consumption
python3 calculate_efficiency_by_tag.py --tag-key Application --output json

# Use a specific AWS profile
python3 calculate_efficiency_by_tag.py --tag-key Application --profile my-profile

# Custom date range (overrides the 30-day rolling default)
python3 calculate_efficiency_by_tag.py --tag-key Application --start-date 2026-06-01 --end-date 2026-07-01
```

## CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `--tag-key` | Tag key to group by (required) | — |
| `--tag-value` | Filter to a specific tag value | All values |
| `--show-resources` | Show per-resource recommendation details | Off |
| `--output` | Output format: `table` or `json` | `table` |
| `--start-date` | Start date (YYYY-MM-DD) | 30 days ago |
| `--end-date` | End date (YYYY-MM-DD) | Today |
| `--profile` | AWS profile name | Default credentials |
| `--region` | AWS region for COH | us-east-1 |

## Output Examples

### Summary Table

```
Cost Efficiency Score by Tag: Application
================================================================================
Tag Value                 |  Optimizable Spend |  Potential Savings | Efficiency
--------------------------------------------------------------------------------
PaymentService            | $       45,230.00 | $        3,200.00 |      92.9%
AuthService               | $       28,100.00 | $        1,450.00 |      94.8%
DataPipeline              | $       67,500.00 | $       12,300.00 |      81.8%
Frontend                  | $       15,800.00 | $          800.00 |      94.9%
--------------------------------------------------------------------------------
TOTAL                     | $      156,630.00 | $       17,750.00 |      88.7%
```

### Resource Details (with --show-resources)

```
Resource Details by Tag: Application
==================================================================
  [DataPipeline] (2 resource(s))
  ----------------------------------------------------------------
  Resource ID                    | Type           | Action    | Savings
  ----------------------------------------------------------------
  my-etl-instance-xl             | Ec2Instance    | Rightsize | $8,500.00
  my-rds-cluster-large           | RdsDbInstance  | Rightsize | $3,800.00
```

## Services in Scope for Total Optimizable Spend

The spend denominator is calculated only for services where Cost Optimization Hub provides recommendations:

- Amazon EC2 (instances, EBS volumes, EBS snapshots)
- Amazon RDS
- Amazon OpenSearch Service
- Amazon ElastiCache
- AWS Lambda
- Amazon ECS (Fargate)
- Amazon Redshift
- Amazon DynamoDB
- Amazon CloudWatch
- Amazon S3

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/efficiency` | Calculate efficiency scores by tag |
| GET | `/api/health` | Health check |

### GET /api/efficiency

Query parameters:
- `tag_key` (required) — Tag key to group by
- `tag_value` (optional) — Filter to specific value
- `show_resources` (optional) — Include resource details (`true`/`false`)
- `profile` (optional) — AWS profile name
- `region` (optional) — AWS region (default: `us-east-1`)

The API always uses a rolling 30-day window for cost data, matching the AWS Console.

## Limitations

- Cost allocation tags must be activated and may take up to 24 hours to appear in billing data.
- Resources without the specified tag are excluded from the calculation.
- Savings Plans and Reserved Instance recommendations are account-level and may not map cleanly to a single tag value.
- The `estimatedMonthlySavings` from Cost Optimization Hub is a point-in-time value based on current resource state, not a historical time series.
- The native `ListEfficiencyMetrics` API only supports grouping by account and region — this tool works around that limitation by combining `ListRecommendations` (tag-filterable) with Cost Explorer.
