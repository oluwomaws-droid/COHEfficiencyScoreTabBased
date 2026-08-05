# Cost Efficiency Formula and Normalization

## The Formula

```
Cost Efficiency = [1 - (Potential Savings / Total Optimizable Spend)] x 100%
```

Where:
- **Potential Savings** = sum of `estimatedMonthlySavings` from all COH recommendations for the tagged resources
- **Total Optimizable Spend** = max(Cost Explorer 30-day AmortizedCost, sum of COH `estimatedMonthlyCost`)

## Why max(CE, COH) for the Denominator

Cost Optimization Hub normalizes monthly costs to a **730-hour month** (365 * 24 / 12). Cost Explorer reports **actual calendar-day spend**.

This creates a mismatch:
- A resource costing $2.40/month in COH terms might only show $2.36 in Cost Explorer's rolling 30-day window due to:
  - Partial days (today's charges not yet complete)
  - Variable month lengths (30 vs 31 days)
  - Time zone differences in daily aggregation

Without the `max()` correction, this mismatch causes `savings > spend`, resulting in negative efficiency scores. Using the higher of the two values ensures:
- When CE has more spend (normal case with many resources): uses CE (captures all resources in supported services, not just those with recommendations)
- When COH cost is higher (edge case with partial billing periods): uses COH (stays consistent with the savings numerator)

## Rolling 30-Day Window

The Cost Optimization Hub console uses a rolling 30-day window for Total Optimizable Spend. This skill uses the same approach:
- End date: today (UTC)
- Start date: 30 days ago (UTC)

## Score Interpretation

| Range | Label | Meaning |
|-------|-------|---------|
| 90-100% | Well optimized | Few or no optimization opportunities exist |
| 70-89% | Needs attention | Notable optimization opportunities — review recommendations |
| Below 70% | Action required | Significant optimization potential — prioritize review |
| 0% | Fully idle/deletable | All spend has equivalent savings (e.g., idle resources recommended for deletion) |
| N/A | Cannot calculate | No optimizable spend found for this tag value |
