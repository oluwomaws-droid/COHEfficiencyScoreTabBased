# Optimizable Services Reference

These are the AWS services included in the Total Optimizable Spend calculation. Only spend on these services is used as the denominator in the Cost Efficiency Score formula, because these are the services where Cost Optimization Hub provides recommendations.

## Service Names (as used in Cost Explorer SERVICE dimension)

| Service Name (Cost Explorer) | Resource Types |
|------------------------------|---------------|
| Amazon Elastic Compute Cloud - Compute | EC2 instances |
| Amazon Elastic Block Store | EBS volumes, snapshots |
| Amazon Relational Database Service | RDS instances, clusters |
| Amazon OpenSearch Service | OpenSearch domains |
| Amazon ElastiCache | ElastiCache clusters |
| AWS Lambda | Lambda functions |
| Amazon Elastic Container Service | ECS/Fargate tasks |
| Amazon Redshift | Redshift clusters |
| Amazon DynamoDB | DynamoDB tables |
| AmazonCloudWatch | CloudWatch logs, metrics |
| Amazon Simple Storage Service | S3 buckets |

## Source

This list is derived from the services documented in the [Cost Optimization Hub cost efficiency documentation](https://docs.aws.amazon.com/cost-management/latest/userguide/coh-cost-efficiency.html).

## Notes

- The list may expand as Cost Optimization Hub adds support for additional services.
- Savings Plans and Reserved Instance recommendations are account-level and span multiple services.
- Some services may appear under different names in Cost Explorer vs the AWS Console (e.g., "EC2 - Other" for EBS in some groupings vs "Amazon Elastic Block Store" when queried directly).
