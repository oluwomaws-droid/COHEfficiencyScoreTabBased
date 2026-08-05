---
name: cost-efficiency-by-tag
description: Calculate the Cost Optimization Hub Cost Efficiency Score grouped by resource tags (e.g., Application, Team, Environment). Combines ListRecommendations with Cost Explorer GetCostAndUsage to produce per-tag efficiency scores not natively available in the console.
---

## Overview

The AWS Cost Optimization Hub provides a Cost Efficiency Score that measures how effectively resources are optimized. The formula is:

```
Cost Efficiency = [1 - (Potential Savings / Total Optimizable Spend)] x 100%
```

The native `ListEfficiencyMetrics` API only supports grouping by **account ID** and **AWS Region**. This skill computes the same metric at the **tag level** by combining two APIs that support tag filtering.

## When to Use This Skill

Use this skill when the customer asks about:
- Cost efficiency per application, team, environment, or any other tag
- Comparing efficiency across tagged workloads
- Which application or team has the most optimization potential
- A cost efficiency breakdown or report by tag

## When NOT to Use This Skill

Do not use this skill when:
- Customer asks for the account-level or region-level efficiency score → use `ListEfficiencyMetrics` directly
- Customer only wants to see recommendations without a score → use `ListRecommendations` directly
- Customer wants to implement or act on optimizations → this skill is informational only

## Workflow

### Step 1: Clarify the Tag

Ask the customer which tag key they want to group by (e.g., `Application`, `Team`, `Environment`, `CostCenter`). If they also specify a tag value, filter to just that value. Otherwise, compute the score for all discovered values of that tag key.

### Step 2: Get Potential Savings from Cost Optimization Hub

Call `cost_optimization` → `list_recommendations` to retrieve recommendations.

**If a specific tag value is provided:**
```
filter: { "tags": [{ "key": "<tag_key>", "value": "<tag_value>" }] }
```

**If computing for all values of a tag key:**
Call `list_recommendations` without a tag-value filter (paginate with `maxResults: 1000`). For each recommendation, inspect the `tags` array to find the value of the requested tag key and group accordingly.

For each recommendation, collect:
- `estimatedMonthlySavings` — contributes to Potential Savings (numerator)
- `estimatedMonthlyCost` — contributes to COH cost baseline (used in denominator)

Sum both values per tag value.

### Step 3: Get Total Optimizable Spend from Cost Explorer

For each tag value discovered in Step 2, call `cost_explorer` → `getCostAndUsage` with:

- **Time period:** Rolling 30 days (today minus 30 days → today)
- **Granularity:** MONTHLY
- **Metrics:** AmortizedCost
- **Filter:** AND combination of:
  - Tag filter: `{ "Key": "<tag_key>", "Values": ["<tag_value>"], "MatchOptions": ["EQUALS"] }`
  - Service filter: `{ "Key": "SERVICE", "Values": [<OPTIMIZABLE_SERVICES>], "MatchOptions": ["EQUALS"] }`

**OPTIMIZABLE_SERVICES** — only these services are in scope for Total Optimizable Spend:
- Amazon Elastic Compute Cloud - Compute
- Amazon Elastic Block Store
- Amazon Relational Database Service
- Amazon OpenSearch Service
- Amazon ElastiCache
- AWS Lambda
- Amazon Elastic Container Service
- Amazon Redshift
- Amazon DynamoDB
- AmazonCloudWatch
- Amazon Simple Storage Service

Sum the `AmortizedCost` across all returned time periods for the tag value.

### Step 4: Calculate the Score

For each tag value:

1. **Determine the denominator (Total Optimizable Spend):**
   ```
   denominator = max(CE_AmortizedCost, sum_of_COH_estimatedMonthlyCost)
   ```
   Use the higher of Cost Explorer's 30-day spend and COH's normalized monthly cost. This prevents negative scores caused by calendar-day vs 730-hour month normalization differences.

2. **Apply the formula:**
   ```
   efficiency_score = [1 - (potential_savings / denominator)] x 100
   ```

3. **Cap the result:** between 0% and 100%.

4. **Handle edge cases:**
   - If denominator is 0 → report "Cannot calculate (no optimizable spend found)"
   - If no recommendations exist for a tag value → report "No recommendations found"

### Step 5: Present Results

Present a summary showing each tag value with:
- Total Optimizable Spend
- Potential Savings
- Efficiency Score (as a percentage)
- A total/aggregate row across all tag values

**Interpretation guidance:**
- 90-100%: Well optimized
- 70-89%: Needs attention — review recommendations
- Below 70%: Action required — significant optimization opportunities exist

If the customer asks for resource details, show the individual recommendations contributing to the savings for each tag value.

## Important Considerations

- **Cost allocation tags must be activated** in the AWS Billing console. If Cost Explorer returns $0 for a tag that clearly has resources, suggest the customer verify the tag is activated.
- **Rolling 30-day window** matches how COH calculates the metric in the console.
- **Untagged resources are excluded.** Only resources with the specified tag contribute to the score.
- **Savings Plans and RI recommendations** are account-level and may not map cleanly to a single tag value. Note this caveat when presenting results that include SP/RI recommendations.
- **The estimatedMonthlySavings from COH is point-in-time** based on current resource state, not a historical time series.

## Guardrails

- **DO NOT** recommend deleting, stopping, or modifying any resources. Present optimization data only.
- **DO NOT** recommend purchasing Savings Plans or Reserved Instances based on the efficiency score.
- **DO NOT** claim this is a native console feature. Note that it is computed using the same formula as the console.
- **DO** acknowledge that untagged resources are excluded from the calculation.
- **DO** point users to the Cost Optimization Hub console for acting on individual recommendations.
- **DO** note that cost allocation tags must be activated for Cost Explorer to recognize them.
