"""
FastAPI backend for the Cost Efficiency Score by Tag UI.

Wraps the Cost Optimization Hub + Cost Explorer logic and exposes it
as a REST API for the Cloudscape frontend to consume.
"""

from datetime import datetime, timedelta
from typing import Optional
import sys
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# Add parent directory to path so we can import the calculation module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calculate_efficiency_by_tag import (
    get_potential_savings_by_tag,
    get_optimizable_spend_by_tag,
    calculate_efficiency_scores,
)

import boto3

app = FastAPI(
    title="Cost Efficiency Score API",
    description="Calculates AWS Cost Optimization Hub efficiency scores grouped by resource tags",
    version="1.0.0",
)

# Allow the Vite dev server to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_default_dates():
    end = datetime.utcnow()
    start = end - timedelta(days=30)  # Rolling 30 days to match AWS Console
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


@app.get("/api/efficiency")
async def get_efficiency(
    tag_key: str = Query(..., description="Tag key to group by, e.g. Application"),
    tag_value: Optional[str] = Query(None, description="Filter to a specific tag value"),
    show_resources: bool = Query(False, description="Include individual resource details"),
    profile: Optional[str] = Query(None, description="AWS profile name"),
    region: str = Query("us-east-1", description="AWS region for Cost Optimization Hub"),
):
    """
    Calculate Cost Efficiency Score grouped by the specified tag key.

    Uses a rolling 30-day spend window to match the AWS Console.
    Returns efficiency scores (using COH formula) per tag value,
    plus optional per-resource recommendation details.
    """
    start, end = get_default_dates()

    # Build boto3 session using ambient credentials (IAM role, env vars, ~/.aws/credentials)
    session_kwargs = {"region_name": region}
    if profile:
        session_kwargs["profile_name"] = profile

    try:
        session = boto3.Session(**session_kwargs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create AWS session: {exc}")

    # Fetch savings from Cost Optimization Hub
    try:
        savings_by_tag, coh_cost_by_tag, resources_by_tag = get_potential_savings_by_tag(
            session, tag_key, tag_value, include_resources=show_resources
        )
    except Exception as exc:
        error_str = str(exc)
        if "AccessDenied" in error_str or "UnauthorizedAccess" in error_str:
            raise HTTPException(
                status_code=403,
                detail="Access denied. Ensure your credentials have cost-optimization-hub:ListRecommendations permission.",
            )
        raise HTTPException(status_code=500, detail=f"Cost Optimization Hub error: {error_str}")

    if not savings_by_tag:
        raise HTTPException(
            status_code=404,
            detail=f"No recommendations found for tag key '{tag_key}'. "
            "Ensure Cost Optimization Hub is enabled and resources are tagged with active cost allocation tags.",
        )

    # Fetch spend from Cost Explorer
    try:
        spend_by_tag = get_optimizable_spend_by_tag(
            session, tag_key, list(savings_by_tag.keys()), start, end
        )
    except Exception as exc:
        error_str = str(exc)
        if "AccessDenied" in error_str:
            raise HTTPException(
                status_code=403,
                detail="Access denied. Ensure your credentials have ce:GetCostAndUsage permission.",
            )
        raise HTTPException(status_code=500, detail=f"Cost Explorer error: {error_str}")

    results = calculate_efficiency_scores(savings_by_tag, spend_by_tag, coh_cost_by_tag)

    total_spend = sum(r["optimizable_spend"] for r in results)
    total_savings = sum(r["potential_savings"] for r in results)
    if total_spend > 0:
        total_score = round(max(0.0, (1 - (total_savings / total_spend)) * 100), 2)
    else:
        total_score = None

    response = {
        "tag_key": tag_key,
        "period": {"start": start, "end": end},
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "results": results,
        "totals": {
            "optimizable_spend": total_spend,
            "potential_savings": total_savings,
            "efficiency_score": total_score,
        },
    }

    if show_resources:
        response["resources"] = resources_by_tag

    return response


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}
