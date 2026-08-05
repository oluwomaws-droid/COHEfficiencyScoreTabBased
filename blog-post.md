# Calculate Cost Efficiency Scores by Tag Using AWS Cost Optimization Hub

[Author Name], Technical Account Manager, AWS

Organizations running workloads at scale on AWS often manage hundreds of applications, each identified by resource tags such as `Application`, `Team`, or `Environment`. While AWS Cost Optimization Hub provides a Cost Efficiency Score at the account and region level, many customers want to measure and track this metric at the tag level to understand cost efficiency on a per-application basis.

The Cost Efficiency Score, introduced in November 2025, uses the formula: `Cost Efficiency = [1 - (Potential Savings / Total Optimizable Spend)] x 100%`. For example, if your Total Optimizable Spend is $100,000 and Cost Optimization Hub identifies $10,000 in potential savings, your Cost Efficiency Score is 90%. Currently, the `ListEfficiencyMetrics` API supports grouping by account ID and AWS Region, but not by tag.

This post shows you how to programmatically calculate the Cost Efficiency Score grouped by any tag key using the Cost Optimization Hub and Cost Explorer APIs. This enables you to benchmark cost efficiency across your application portfolio, set optimization targets per team, and track progress over time.

## Overview of solution

The solution combines two AWS APIs that support tag-based filtering to reconstruct the Cost Efficiency Score formula at the tag level:

1. **Cost Optimization Hub `ListRecommendationSummaries`** — supports a `tags` filter, providing the deduped Potential Savings for resources matching a specific tag. `ListRecommendations` supplements with `estimatedMonthlyCost` for the denominator.
2. **AWS Cost Explorer `GetCostAndUsage`** — supports filtering by tag and service, providing the Total Optimizable Spend scoped to services where Cost Optimization Hub provides recommendations.

The following diagram shows how the solution retrieves data from both APIs and combines them to produce a per-tag efficiency score:

```
┌─────────────────────────────────────┐
│         Python CLI Script           │
└──────────────┬──────────────────────┘
               │
       ┌───────┴───────┐
       │               │
       ▼               ▼
┌──────────────┐  ┌──────────────────┐
│    Cost      │  │   AWS Cost       │
│ Optimization │  │   Explorer       │
│    Hub       │  │                  │
│              │  │ GetCostAndUsage  │
│ ListRecSumm  │  │ (tag + service   │
│ (tag filter) │  │  filter)         │
└──────┬───────┘  └────────┬─────────┘
       │                   │
       ▼                   ▼
  Potential            Total Optimizable
  Savings (deduped)    Spend (30-day)
       │                   │
       └─────────┬─────────┘
                 ▼
     max(CE Spend, COH Cost)
     as denominator
                 │
                 ▼
        Cost Efficiency Score
        per Tag Value
```

The solution uses a rolling 30-day window for cost data, matching how the Cost Optimization Hub console calculates the metric. For the denominator, it uses the higher of Cost Explorer spend and Cost Optimization Hub's normalized monthly cost to avoid edge cases caused by calendar-day versus 730-hour month normalization differences.

## Walkthrough

This walkthrough guides you through building a Python script that calculates the Cost Efficiency Score for each value of a specified tag key. The steps are:

1. Set up prerequisites and define services in scope
2. Retrieve Potential Savings from Cost Optimization Hub
3. Retrieve Total Optimizable Spend from Cost Explorer
4. Calculate the Cost Efficiency Score
5. Run the solution

### Prerequisites

For this walkthrough, you should have the following prerequisites:

- An AWS account with Cost Optimization Hub enabled
- Cost allocation tags activated in the AWS Billing console
- Python 3.9 or later with `boto3` installed (`pip install boto3`)
- IAM permissions for `cost-optimization-hub:ListRecommendations`, `cost-optimization-hub:ListRecommendationSummaries`, and `ce:GetCostAndUsage`

### Define services in scope

Total Optimizable Spend only includes services where Cost Optimization Hub provides recommendations. Define these as a constant in your script:

```python
OPTIMIZABLE_SERVICES = [
    "Amazon Elastic Compute Cloud - Compute",
    "Amazon Elastic Block Store",
    "Amazon Relational Database Service",
    "Amazon OpenSearch Service",
    "Amazon ElastiCache",
    "AWS Lambda",
    "Amazon Elastic Container Service",
    "Amazon Redshift",
    "Amazon DynamoDB",
    "AmazonCloudWatch",
    "Amazon Simple Storage Service",
]
```

### Retrieve Potential Savings from Cost Optimization Hub

Use the `ListRecommendationSummaries` API with a tag filter to get the **deduped** estimated monthly savings. This API internally deduplicates savings across resource types, matching how efficiency metrics are calculated in the console.

```python
import boto3
from botocore.config import Config

def get_deduped_savings_for_tag(session, tag_key, tag_value):
    """Get deduped potential savings using ListRecommendationSummaries."""
    client = session.client(
        "cost-optimization-hub",
        config=Config(retries={"max_attempts": 5, "mode": "adaptive"}),
    )

    response = client.list_recommendation_summaries(
        filter={"tags": [{"key": tag_key, "value": tag_value}]},
        groupBy="ResourceType",
        maxResults=1000,
    )

    # estimatedTotalDedupedSavings is the authoritative deduped total
    return response.get("estimatedTotalDedupedSavings", 0.0)
```

You also need the `estimatedMonthlyCost` from `ListRecommendations` for the denominator calculation (explained in Step 4):

```python
def get_coh_cost_for_tag(session, tag_key, tag_value):
    """Get sum of estimatedMonthlyCost for the denominator."""
    client = session.client(
        "cost-optimization-hub",
        config=Config(retries={"max_attempts": 5, "mode": "adaptive"}),
    )

    total_coh_cost = 0.0
    next_token = None

    while True:
        params = {
            "filter": {"tags": [{"key": tag_key, "value": tag_value}]},
            "maxResults": 1000,
        }
        if next_token:
            params["nextToken"] = next_token

        response = client.list_recommendations(**params)

        for rec in response.get("items", []):
            total_coh_cost += rec.get("estimatedMonthlyCost", 0.0)

        next_token = response.get("nextToken")
        if not next_token:
            break

    return total_coh_cost
```

### Retrieve Total Optimizable Spend from Cost Explorer

Query Cost Explorer for the amortized cost of the tagged resources, filtered to only the services in scope. Use a rolling 30-day window to match how Cost Optimization Hub calculates the metric in the console.

```python
from datetime import datetime, timedelta

def get_optimizable_spend(session, tag_key, tag_value):
    """Get 30-day optimizable spend for a tag value from Cost Explorer."""
    client = session.client("ce")

    end_date = datetime.utcnow().strftime("%Y-%m-%d")
    start_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")

    response = client.get_cost_and_usage(
        TimePeriod={"Start": start_date, "End": end_date},
        Granularity="MONTHLY",
        Metrics=["AmortizedCost"],
        Filter={
            "And": [
                {
                    "Tags": {
                        "Key": tag_key,
                        "Values": [tag_value],
                        "MatchOptions": ["EQUALS"],
                    }
                },
                {
                    "Dimensions": {
                        "Key": "SERVICE",
                        "Values": OPTIMIZABLE_SERVICES,
                        "MatchOptions": ["EQUALS"],
                    }
                },
            ]
        },
    )

    total_cost = 0.0
    for result in response.get("ResultsByTime", []):
        amount = result["Total"]["AmortizedCost"]["Amount"]
        total_cost += float(amount)

    return total_cost
```

### Calculate the Cost Efficiency Score

Cost Optimization Hub normalizes costs to a 730-hour month, while Cost Explorer reports actual calendar-day spend. To handle edge cases where this mismatch causes savings to slightly exceed spend, use the higher of the two cost sources as the denominator:

```python
def calculate_efficiency(potential_savings, ce_spend, coh_cost):
    """
    Calculate Cost Efficiency Score.

    Uses max(CE spend, COH cost) as denominator to prevent
    calendar-day vs 730-hour normalization mismatches.
    """
    optimizable_spend = max(ce_spend, coh_cost)

    if optimizable_spend <= 0:
        return None

    score = (1 - (potential_savings / optimizable_spend)) * 100
    return max(0.0, min(100.0, score))
```

### Run the solution

Put the functions together and run the script:

```python
def main():
    session = boto3.Session(region_name="us-east-1")
    tag_key = "Application"
    tag_value = "PaymentService"

    # Get deduped savings from ListRecommendationSummaries
    potential_savings = get_deduped_savings_for_tag(session, tag_key, tag_value)

    # Get COH cost for denominator
    coh_cost = get_coh_cost_for_tag(session, tag_key, tag_value)

    # Get actual spend from Cost Explorer
    ce_spend = get_optimizable_spend(session, tag_key, tag_value)

    # Calculate the score
    score = calculate_efficiency(potential_savings, ce_spend, coh_cost)

    print(f"Application: {tag_value}")
    print(f"  Total Optimizable Spend: ${max(ce_spend, coh_cost):,.2f}")
    print(f"  Potential Savings:       ${potential_savings:,.2f}")
    print(f"  Cost Efficiency Score:   {score:.1f}%")

if __name__ == "__main__":
    main()
```

Running this produces output similar to:

```
Application: PaymentService
  Total Optimizable Spend: $45,230.00
  Potential Savings:       $3,200.00
  Cost Efficiency Score:   92.9%
```

To scale this across all values of a tag key, first discover all tag values by scanning recommendations, then call `get_deduped_savings_for_tag` for each:

```python
def discover_tag_values(session, tag_key):
    """Discover all values for a tag key by scanning recommendations."""
    client = session.client(
        "cost-optimization-hub",
        config=Config(retries={"max_attempts": 5, "mode": "adaptive"}),
    )

    tag_values = set()
    next_token = None

    while True:
        params = {"maxResults": 1000}
        if next_token:
            params["nextToken"] = next_token

        response = client.list_recommendations(**params)

        for rec in response.get("items", []):
            for tag in rec.get("tags", []):
                if tag.get("key") == tag_key:
                    tag_values.add(tag["value"])
                    break

        next_token = response.get("nextToken")
        if not next_token:
            break

    return sorted(tag_values)
```

You can then loop through each discovered tag value, call `get_deduped_savings_for_tag` and `get_optimizable_spend` for each, and calculate individual scores to produce a report like:

```
Cost Efficiency Score by Tag: Application
================================================================================
Tag Value                 |  Optimizable Spend |  Potential Savings | Efficiency
--------------------------------------------------------------------------------
AuthService               | $       28,100.00 | $        1,450.00 |      94.8%
Frontend                  | $       15,800.00 | $          800.00 |      94.9%
PaymentService            | $       45,230.00 | $        3,200.00 |      92.9%
DataPipeline              | $       67,500.00 | $       12,300.00 |      81.8%
--------------------------------------------------------------------------------
TOTAL                     | $      156,630.00 | $       17,750.00 |      88.7%
```

### Cleaning up

This solution only performs read operations against Cost Optimization Hub and Cost Explorer. There are no resources to delete. If you deployed the script to AWS Lambda or Amazon EC2 for scheduled execution, delete those resources to avoid incurring future charges.

## Conclusion

In this post, you learned how to calculate the AWS Cost Optimization Hub Cost Efficiency Score at the tag level by combining the `ListRecommendations` API with the Cost Explorer `GetCostAndUsage` API. This approach fills the gap where the native `ListEfficiencyMetrics` API only supports grouping by account and region.

You can extend this solution by:

- Scheduling the script with AWS Lambda and Amazon EventBridge to run daily, storing results in Amazon DynamoDB to track efficiency trends over time
- Building a dashboard in Amazon QuickSight to visualize efficiency scores across your application portfolio
- Setting up Amazon CloudWatch alarms to notify when an application's efficiency drops below a threshold

For more information about the Cost Efficiency Score, see [Understanding your cost efficiency metric](https://docs.aws.amazon.com/cost-management/latest/userguide/coh-cost-efficiency.html) in the AWS documentation.

### Author bio

[Author Name] is a Technical Account Manager at AWS, helping customers optimize their cloud investments through AWS Cost Management services.

Suggested tags: cost-optimization, cost-optimization-hub, cost-explorer, finops, tagging
