# Calculate Cost Efficiency Scores by Tag Using AWS Cost Optimization Hub APIs

Organizations running workloads at scale on AWS often manage hundreds of applications, each identified by resource tags such as `Application`, `Team`, or `Environment`. While [AWS Cost Optimization Hub](https://docs.aws.amazon.com/cost-management/latest/userguide/cost-optimization-hub.html) provides a Cost Efficiency Score at the account and region level, many customers want to measure and track this metric at the **tag level** to understand cost efficiency on a per-application basis.

In this post, we show you how to programmatically calculate the Cost Efficiency Score grouped by any tag key using the Cost Optimization Hub and AWS Cost Explorer APIs. This approach enables you to benchmark cost efficiency across your application portfolio, set optimization targets per team, and track progress over time.

## Background: The Cost Efficiency Score

The Cost Efficiency Score, [introduced in November 2025](https://aws.amazon.com/about-aws/whats-new/2025/11/aws-cost-optimization-hub-cost-efficiency-metric-measure-track/), provides a single metric that measures how effectively you are optimizing your cloud resources. The formula is:

```
Cost Efficiency = [1 - (Potential Savings / Total Optimizable Spend)] x 100%
```

Where:

- **Potential Savings** is the sum of estimated monthly savings from all recommendations identified by Cost Optimization Hub (rightsizing, idle resources, commitment-based discounts, and more).
- **Total Optimizable Spend** is your spend on services where Cost Optimization Hub provides recommendations, such as Amazon EC2, Amazon RDS, AWS Lambda, and Amazon S3.

For example, if your Total Optimizable Spend is $100,000 and Cost Optimization Hub identifies $10,000 in potential savings, your Cost Efficiency Score is 90%.

## Solution overview

Today, the [ListEfficiencyMetrics](https://docs.aws.amazon.com/cli/latest/reference/cost-optimization-hub/list-efficiency-metrics.html) API supports grouping by account ID and AWS Region, but not by tag. However, we can reconstruct the same formula at the tag level by combining two APIs that do support tag filtering:

1. **Cost Optimization Hub `ListRecommendations`** — supports a `tags` filter, giving us the Potential Savings for resources matching a specific tag.
2. **AWS Cost Explorer `GetCostAndUsage`** — supports filtering by tag and grouping by service, giving us the Total Optimizable Spend.

The following diagram illustrates the solution architecture:

```
┌─────────────────────────────────────┐
│         Your Script / CLI           │
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
│ ListRecs     │  │ (tag + service   │
│ (tag filter) │  │  filter)         │
└──────┬───────┘  └────────┬─────────┘
       │                   │
       ▼                   ▼
  Potential            Total Optimizable
  Savings              Spend (30-day)
       │                   │
       └─────────┬─────────┘
                 ▼
        Cost Efficiency Score
        per Tag Value
```

## Prerequisites

Before you begin, ensure you have the following:

- An AWS account with [Cost Optimization Hub enabled](https://docs.aws.amazon.com/cost-management/latest/userguide/cost-optimization-hub.html)
- [Cost allocation tags activated](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/activating-tags.html) in the AWS Billing console
- Python 3.9 or later with `boto3` installed
- IAM permissions for:
  - `cost-optimization-hub:ListRecommendations`
  - `ce:GetCostAndUsage`

## Walkthrough

### Step 1: Define the services in scope

Total Optimizable Spend only includes services where Cost Optimization Hub provides recommendations. Define these services as a constant:

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

### Step 2: Retrieve Potential Savings from Cost Optimization Hub

Use the `ListRecommendations` API with a tag filter to get the estimated monthly savings for all resources matching your tag. The API also returns `estimatedMonthlyCost` for each recommendation, which we collect for use in Step 4.

```python
import boto3
from botocore.config import Config

def get_savings_for_tag(session, tag_key, tag_value):
    """Get potential savings and COH-estimated cost for a tag value."""
    client = session.client(
        "cost-optimization-hub",
        config=Config(retries={"max_attempts": 5, "mode": "adaptive"}),
    )

    total_savings = 0.0
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
            total_savings += rec.get("estimatedMonthlySavings", 0.0)
            total_coh_cost += rec.get("estimatedMonthlyCost", 0.0)

        next_token = response.get("nextToken")
        if not next_token:
            break

    return total_savings, total_coh_cost
```

### Step 3: Retrieve Total Optimizable Spend from Cost Explorer

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

### Step 4: Calculate the Cost Efficiency Score

Cost Optimization Hub normalizes costs to a 730-hour month, while Cost Explorer reports actual calendar-day spend. This can cause the Potential Savings to slightly exceed the Cost Explorer spend for resources in a partial billing period. To handle this edge case, use the higher of the two cost sources as the denominator:

```python
def calculate_efficiency(potential_savings, ce_spend, coh_cost):
    """
    Calculate Cost Efficiency Score.
    
    Uses max(CE spend, COH cost) as denominator to prevent
    calendar-day vs 730-hour normalization mismatches.
    """
    optimizable_spend = max(ce_spend, coh_cost)

    if optimizable_spend <= 0:
        return None  # Cannot calculate without spend data

    score = (1 - (potential_savings / optimizable_spend)) * 100
    return max(0.0, min(100.0, score))  # Cap between 0-100%
```

### Step 5: Put it all together

```python
def main():
    session = boto3.Session(region_name="us-east-1")
    tag_key = "Application"

    # Example: calculate efficiency for a specific application
    tag_value = "PaymentService"

    # Get savings and COH cost from Cost Optimization Hub
    potential_savings, coh_cost = get_savings_for_tag(session, tag_key, tag_value)

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

### Step 6: Scale across all tag values

To calculate the score across all values of a tag key (for example, all applications), retrieve all recommendations without a tag-value filter and group them by the tag:

```python
def get_all_savings_by_tag(session, tag_key):
    """Pull all recommendations and group by tag key."""
    client = session.client(
        "cost-optimization-hub",
        config=Config(retries={"max_attempts": 5, "mode": "adaptive"}),
    )

    savings_by_tag = {}
    coh_cost_by_tag = {}
    next_token = None

    while True:
        params = {"maxResults": 1000}
        if next_token:
            params["nextToken"] = next_token

        response = client.list_recommendations(**params)

        for rec in response.get("items", []):
            for tag in rec.get("tags", []):
                if tag.get("key") == tag_key:
                    tv = tag["value"]
                    savings_by_tag[tv] = savings_by_tag.get(tv, 0.0) + rec.get("estimatedMonthlySavings", 0.0)
                    coh_cost_by_tag[tv] = coh_cost_by_tag.get(tv, 0.0) + rec.get("estimatedMonthlyCost", 0.0)
                    break

        next_token = response.get("nextToken")
        if not next_token:
            break

    return savings_by_tag, coh_cost_by_tag
```

You can then loop through each discovered tag value, call `get_optimizable_spend` for each, and calculate individual scores to produce a report like:

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

## Key considerations

**Cost allocation tags must be activated.** Tags must be activated in the AWS Billing console before they appear in Cost Explorer data. It can take up to 24 hours for newly activated tags to propagate.

**Rolling 30-day window.** The Cost Optimization Hub console uses a rolling 30-day window for the Total Optimizable Spend. This solution uses the same approach to produce comparable results.

**Handling the cost normalization mismatch.** Cost Optimization Hub estimates monthly cost using a standardized 730-hour month, while Cost Explorer reports actual calendar-day spend. For resources in partial billing periods, this can cause the savings to slightly exceed the Cost Explorer spend. The solution handles this by using `max(CE spend, COH estimated cost)` as the denominator.

**Savings Plans and Reserved Instance recommendations** are account-level and may not map cleanly to a single tag value. If your organization uses these commitment-based recommendations, consider how they should be attributed across applications.

**API throttling.** If you have a large number of recommendations or tag values, implement appropriate retry logic and consider paginating requests efficiently. The code samples above use adaptive retry mode to handle this.

## Conclusion

In this post, we showed how to calculate the AWS Cost Optimization Hub Cost Efficiency Score at the tag level by combining the `ListRecommendations` API (for Potential Savings) with the Cost Explorer `GetCostAndUsage` API (for Total Optimizable Spend). This approach lets you measure and track cost efficiency per application, team, or any other tag dimension in your AWS environment.

You can extend this solution by:

- Scheduling the script to run daily and storing results in Amazon DynamoDB or Amazon S3 to track efficiency trends over time
- Building a dashboard in Amazon QuickSight to visualize efficiency scores across your application portfolio
- Setting up Amazon EventBridge rules to alert when an application's efficiency drops below a threshold
- Integrating the scores into your existing FinOps reporting workflows

For more information about the Cost Efficiency Score, see [Understanding your cost efficiency metric](https://docs.aws.amazon.com/cost-management/latest/userguide/coh-cost-efficiency.html) in the AWS documentation.

---

**About the authors**

*Wole Modupe* is .....
*Jacob Scheatzle* is .....
*Joe Rader* is .....


