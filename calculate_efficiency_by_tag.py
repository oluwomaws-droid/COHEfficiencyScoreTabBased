#!/usr/bin/env python3
"""
Calculate AWS Cost Optimization Hub Cost Efficiency Score by Tag.

This script computes the Cost Efficiency Score per tag value using:
- Cost Optimization Hub API for Potential Savings (filtered by tag)
- Cost Explorer API for Total Optimizable Spend (filtered by tag and scoped to COH services)

Formula: Cost Efficiency = [1 - (Potential Savings / Total Optimizable Spend)] x 100%
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from typing import Optional

import boto3
from botocore.config import Config


# Services in scope for Total Optimizable Spend in Cost Optimization Hub.
# These are the services where COH provides optimization recommendations.
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


def get_potential_savings_by_tag(
    session: boto3.Session,
    tag_key: str,
    tag_value: Optional[str] = None,
    include_resources: bool = False,
) -> tuple[dict[str, float], dict[str, float], dict[str, list[dict]]]:
    """
    Query Cost Optimization Hub for potential savings grouped by tag value.

    Uses ListRecommendationSummaries with groupBy=TagKey:<key> to get deduped
    savings per tag value in a single API call.

    Returns a tuple of:
      - dict mapping tag_value -> estimated_monthly_savings (deduped)
      - dict mapping tag_value -> estimated_monthly_cost (sum from COH recommendations)
      - dict mapping tag_value -> list of resource details (if include_resources=True)
    """
    client = session.client(
        "cost-optimization-hub",
        config=Config(retries={"max_attempts": 5, "mode": "adaptive"}),
    )

    # Get deduped savings per tag value using groupBy=TagKey:<key>
    savings_by_tag = _get_deduped_savings_by_tag(client, tag_key, tag_value)

    if not savings_by_tag:
        return {}, {}, {}

    # Determine which tag values to get cost/resources for
    tag_values = [tag_value] if tag_value else list(savings_by_tag.keys())

    # Get estimatedMonthlyCost (and resources if requested) from ListRecommendations
    coh_cost_by_tag: dict[str, float] = {}
    resources_by_tag: dict[str, list[dict]] = {}

    for tv in tag_values:
        if tv not in savings_by_tag:
            continue
        coh_cost, resources = _get_cost_and_resources_for_tag(
            client, tag_key, tv, include_resources
        )
        coh_cost_by_tag[tv] = coh_cost
        if include_resources:
            resources_by_tag[tv] = resources

    return savings_by_tag, coh_cost_by_tag, resources_by_tag


def _get_deduped_savings_by_tag(
    client, tag_key: str, tag_value: Optional[str] = None
) -> dict[str, float]:
    """
    Get deduped savings grouped by tag value using ListRecommendationSummaries
    with groupBy=TagKey:<key>.

    Returns a dict mapping tag_value -> deduped_savings.
    Excludes the "NoTagKey" group (resources without this tag).
    """
    savings_by_tag: dict[str, float] = {}
    next_token = None

    while True:
        params: dict = {
            "groupBy": f"TagKey:{tag_key}",
            "maxResults": 1000,
        }
        # If filtering to a specific tag value, add the filter
        if tag_value:
            params["filter"] = {
                "tags": [{"key": tag_key, "value": tag_value}]
            }
        if next_token:
            params["nextToken"] = next_token

        response = client.list_recommendation_summaries(**params)

        for item in response.get("items", []):
            group = item.get("group", "")
            # Skip resources that don't have this tag
            if group == "NoTagKey":
                continue
            savings = item.get("estimatedMonthlySavings", 0.0)
            savings_by_tag[group] = savings_by_tag.get(group, 0.0) + savings

        next_token = response.get("nextToken")
        if not next_token:
            break

    return savings_by_tag


def _get_cost_and_resources_for_tag(
    client, tag_key: str, tag_value: str, include_resources: bool = False
) -> tuple[float, list[dict]]:
    """
    Get estimatedMonthlyCost and resource details from ListRecommendations.

    Used for the denominator calculation (COH cost) and optional resource detail view.
    """
    total_coh_cost = 0.0
    resources: list[dict] = []
    paginator_params = {
        "filter": {
            "tags": [{"key": tag_key, "value": tag_value}]
        },
        "maxResults": 1000,
    }

    next_token = None
    while True:
        if next_token:
            paginator_params["nextToken"] = next_token

        response = client.list_recommendations(**paginator_params)

        for rec in response.get("items", []):
            total_coh_cost += rec.get("estimatedMonthlyCost", 0.0)
            if include_resources:
                resources.append(_extract_resource_info(rec))

        next_token = response.get("nextToken")
        if not next_token:
            break

    return total_coh_cost, resources


def _extract_resource_info(rec: dict) -> dict:
    """Extract relevant resource info from a recommendation item."""
    return {
        "resource_id": rec.get("resourceId", "N/A"),
        "resource_arn": rec.get("resourceArn", "N/A"),
        "resource_type": rec.get("currentResourceType", rec.get("resourceType", "N/A")),
        "action_type": rec.get("actionType", "N/A"),
        "estimated_monthly_savings": rec.get("estimatedMonthlySavings", 0.0),
        "estimated_monthly_cost": rec.get("estimatedMonthlyCost", 0.0),
        "estimated_savings_percentage": rec.get("estimatedSavingsPercentage", 0.0),
        "current_resource_summary": rec.get("currentResourceSummary", "N/A"),
        "recommended_resource_summary": rec.get("recommendedResourceSummary", "N/A"),
        "account_id": rec.get("accountId", "N/A"),
        "region": rec.get("region", "N/A"),
        "recommendation_id": rec.get("recommendationId", "N/A"),
    }


def get_optimizable_spend_by_tag(
    session: boto3.Session,
    tag_key: str,
    tag_values: list[str],
    start_date: str,
    end_date: str,
) -> dict[str, float]:
    """
    Query Cost Explorer for Total Optimizable Spend per tag value.

    Filters to only the services in scope for Cost Optimization Hub.
    Uses NetAmortizedCost to match COH methodology — this is amortized cost
    with credits and refunds removed, per the Cost Optimization Hub docs.
    """
    client = session.client("ce")
    spend_by_tag: dict[str, float] = {}

    for tv in tag_values:
        response = client.get_cost_and_usage(
            TimePeriod={"Start": start_date, "End": end_date},
            Granularity="MONTHLY",
            Metrics=["NetAmortizedCost"],
            Filter={
                "And": [
                    {
                        "Tags": {
                            "Key": tag_key,
                            "Values": [tv],
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
            amount = result.get("Total", {}).get("NetAmortizedCost", {}).get("Amount", "0")
            total_cost += float(amount)

        spend_by_tag[tv] = total_cost

    return spend_by_tag


def calculate_efficiency_scores(
    savings_by_tag: dict[str, float],
    spend_by_tag: dict[str, float],
    coh_cost_by_tag: Optional[dict[str, float]] = None,
) -> list[dict]:
    """
    Calculate Cost Efficiency Score for each tag value.

    Formula: Cost Efficiency = [1 - (Potential Savings / Total Optimizable Spend)] x 100

    For the denominator (Total Optimizable Spend), uses the higher of:
      - Cost Explorer's 30-day amortized spend (captures all resources in supported services)
      - Sum of COH's estimatedMonthlyCost for recommended resources (730-hour normalized)

    This prevents the calendar-day vs 730-hour mismatch from producing negative scores.
    """
    results = []

    for tag_value in sorted(savings_by_tag.keys()):
        potential_savings = savings_by_tag.get(tag_value, 0.0)
        ce_spend = spend_by_tag.get(tag_value, 0.0)
        coh_cost = (coh_cost_by_tag or {}).get(tag_value, 0.0)

        # Use the higher of CE spend and COH cost as the denominator
        # CE spend covers all resources; COH cost is 730-hour normalized for recommended ones
        optimizable_spend = max(ce_spend, coh_cost)

        if optimizable_spend > 0:
            efficiency_score = (1 - (potential_savings / optimizable_spend)) * 100
            # Cap at 0-100 range
            efficiency_score = max(0.0, min(100.0, efficiency_score))
        else:
            efficiency_score = None  # Cannot calculate without spend data

        results.append(
            {
                "tag_value": tag_value,
                "optimizable_spend": optimizable_spend,
                "potential_savings": potential_savings,
                "efficiency_score": efficiency_score,
            }
        )

    return results


def print_table(tag_key: str, results: list[dict], resources_by_tag: Optional[dict[str, list[dict]]] = None) -> None:
    """Print results as a formatted table."""
    print(f"\nCost Efficiency Score by Tag: {tag_key}")
    print("=" * 80)
    print(
        f"{'Tag Value':<25} | {'Optimizable Spend':>18} | "
        f"{'Potential Savings':>18} | {'Efficiency':>10}"
    )
    print("-" * 80)

    total_spend = 0.0
    total_savings = 0.0

    for row in results:
        tag_val = row["tag_value"][:24]
        spend = row["optimizable_spend"]
        savings = row["potential_savings"]
        score = row["efficiency_score"]

        total_spend += spend
        total_savings += savings

        score_str = f"{score:.1f}%" if score is not None else "N/A"
        print(f"{tag_val:<25} | ${spend:>16,.2f} | ${savings:>16,.2f} | {score_str:>10}")

    print("-" * 80)

    if total_spend > 0:
        total_score = (1 - (total_savings / total_spend)) * 100
        total_score = max(0.0, min(100.0, total_score))
        total_score_str = f"{total_score:.1f}%"
    else:
        total_score_str = "N/A"

    print(
        f"{'TOTAL':<25} | ${total_spend:>16,.2f} | "
        f"${total_savings:>16,.2f} | {total_score_str:>10}"
    )
    print()

    # Print resource details if requested
    if resources_by_tag:
        print_resources_table(tag_key, resources_by_tag)


def print_resources_table(tag_key: str, resources_by_tag: dict[str, list[dict]]) -> None:
    """Print detailed resource list grouped by tag value."""
    print(f"\nResource Details by Tag: {tag_key}")
    print("=" * 140)

    for tag_value in sorted(resources_by_tag.keys()):
        resources = resources_by_tag[tag_value]
        if not resources:
            continue

        # Sort resources by savings descending
        resources_sorted = sorted(
            resources, key=lambda r: r["estimated_monthly_savings"], reverse=True
        )

        print(f"\n  [{tag_value}] ({len(resources_sorted)} resource(s))")
        print(f"  {'-' * 136}")
        print(
            f"  {'Resource ID':<45} | {'Type':<16} | {'Action':<10} | "
            f"{'Region':<14} | {'Account':<13} | {'Savings':>10} | {'Recommendation':<20}"
        )
        print(f"  {'-' * 136}")

        for res in resources_sorted:
            res_id = res["resource_id"][:44]
            res_type = res["resource_type"][:15]
            action = res["action_type"][:9]
            region = res["region"][:13]
            account = res["account_id"][:12]
            savings = res["estimated_monthly_savings"]
            current = res.get("current_resource_summary", "")
            recommended = res.get("recommended_resource_summary", "")
            rec_detail = f"{current} -> {recommended}" if current and recommended else ""
            rec_detail = rec_detail[:19]

            # Use more decimal places for small savings values
            if savings < 0.01:
                savings_str = f"${savings:>9.4f}"
            else:
                savings_str = f"${savings:>9,.2f}"

            print(
                f"  {res_id:<45} | {res_type:<16} | {action:<10} | "
                f"{region:<14} | {account:<13} | {savings_str} | {rec_detail:<20}"
            )

    print()
    print("=" * 140)
    print()


def print_json(tag_key: str, results: list[dict], resources_by_tag: Optional[dict[str, list[dict]]] = None) -> None:
    """Print results as JSON."""
    output = {
        "tag_key": tag_key,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "results": results,
        "totals": {
            "optimizable_spend": sum(r["optimizable_spend"] for r in results),
            "potential_savings": sum(r["potential_savings"] for r in results),
        },
    }
    total_spend = output["totals"]["optimizable_spend"]
    total_savings = output["totals"]["potential_savings"]
    if total_spend > 0:
        output["totals"]["efficiency_score"] = round(
            max(0.0, (1 - (total_savings / total_spend)) * 100), 2
        )
    else:
        output["totals"]["efficiency_score"] = None

    if resources_by_tag:
        output["resources"] = resources_by_tag

    print(json.dumps(output, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(
        description="Calculate Cost Efficiency Score by Tag using Cost Optimization Hub"
    )
    parser.add_argument(
        "--tag-key",
        required=True,
        help="The tag key to group by (e.g., Application, Team, Environment)",
    )
    parser.add_argument(
        "--tag-value",
        help="Optional: calculate only for a specific tag value",
    )
    parser.add_argument(
        "--start-date",
        help="Start date for cost data (YYYY-MM-DD). Default: 30 days ago (rolling window)",
    )
    parser.add_argument(
        "--end-date",
        help="End date for cost data (YYYY-MM-DD). Default: today",
    )
    parser.add_argument(
        "--output",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--show-resources",
        action="store_true",
        help="Include a detailed list of resources with recommendations after the summary",
    )
    parser.add_argument(
        "--profile",
        help="AWS profile name to use",
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region for Cost Optimization Hub (default: us-east-1)",
    )

    args = parser.parse_args()

    # Set date range (default: rolling 30 days to match AWS Console)
    now = datetime.utcnow()
    if args.end_date:
        end_date = args.end_date
    else:
        end_date = now.strftime("%Y-%m-%d")

    if args.start_date:
        start_date = args.start_date
    else:
        start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")

    # Create session
    session_kwargs = {}
    if args.profile:
        session_kwargs["profile_name"] = args.profile
    if args.region:
        session_kwargs["region_name"] = args.region

    session = boto3.Session(**session_kwargs)

    print(f"Fetching potential savings from Cost Optimization Hub...", file=sys.stderr)
    savings_by_tag, coh_cost_by_tag, resources_by_tag = get_potential_savings_by_tag(
        session, args.tag_key, args.tag_value, include_resources=args.show_resources
    )

    if not savings_by_tag:
        print(
            f"No recommendations found with tag key '{args.tag_key}'. "
            "Ensure Cost Optimization Hub is enabled and resources are tagged.",
            file=sys.stderr,
        )
        sys.exit(1)

    tag_values = list(savings_by_tag.keys())
    print(
        f"Found {len(tag_values)} tag value(s). Fetching cost data from Cost Explorer...",
        file=sys.stderr,
    )

    spend_by_tag = get_optimizable_spend_by_tag(
        session, args.tag_key, tag_values, start_date, end_date
    )

    results = calculate_efficiency_scores(savings_by_tag, spend_by_tag, coh_cost_by_tag)

    if args.output == "json":
        print_json(args.tag_key, results, resources_by_tag if args.show_resources else None)
    else:
        print_table(args.tag_key, results, resources_by_tag if args.show_resources else None)


if __name__ == "__main__":
    main()
