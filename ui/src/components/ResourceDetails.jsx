import React, { useState } from 'react';
import Table from '@cloudscape-design/components/table';
import Header from '@cloudscape-design/components/header';
import Box from '@cloudscape-design/components/box';
import ExpandableSection from '@cloudscape-design/components/expandable-section';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Badge from '@cloudscape-design/components/badge';
import Link from '@cloudscape-design/components/link';
import Container from '@cloudscape-design/components/container';

function formatCurrency(value) {
  if (value === null || value === undefined) return '-';
  if (value < 0.01 && value > 0) {
    return `$${value.toFixed(4)}`;
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function getActionBadgeColor(action) {
  switch (action) {
    case 'Rightsize': return 'blue';
    case 'Stop': return 'red';
    case 'Delete': return 'red';
    case 'Upgrade': return 'green';
    case 'MigrateToGraviton': return 'green';
    case 'PurchaseSavingsPlans': return 'grey';
    case 'PurchaseReservedInstances': return 'grey';
    default: return 'grey';
  }
}

const COLUMN_DEFINITIONS = [
  {
    id: 'resource_id',
    header: 'Resource ID',
    cell: (item) => (
      <Link href={`https://console.aws.amazon.com/resource-groups/tag-editor/find-resources?region=${item.region}`} external>
        {item.resource_id}
      </Link>
    ),
    sortingField: 'resource_id',
    width: 300,
  },
  {
    id: 'resource_type',
    header: 'Resource type',
    cell: (item) => item.resource_type || '-',
    sortingField: 'resource_type',
    width: 140,
  },
  {
    id: 'action_type',
    header: 'Action',
    cell: (item) => <Badge color={getActionBadgeColor(item.action_type)}>{item.action_type}</Badge>,
    sortingField: 'action_type',
    width: 120,
  },
  {
    id: 'current_resource_summary',
    header: 'Current',
    cell: (item) => item.current_resource_summary || '-',
    width: 150,
  },
  {
    id: 'recommended_resource_summary',
    header: 'Recommended',
    cell: (item) => item.recommended_resource_summary || '-',
    width: 150,
  },
  {
    id: 'region',
    header: 'Region',
    cell: (item) => item.region,
    sortingField: 'region',
    width: 130,
  },
  {
    id: 'account_id',
    header: 'Account',
    cell: (item) => item.account_id,
    sortingField: 'account_id',
    width: 130,
  },
  {
    id: 'estimated_monthly_savings',
    header: 'Monthly savings',
    cell: (item) => (
      <Box color="text-status-success" fontWeight="bold">
        {formatCurrency(item.estimated_monthly_savings)}
      </Box>
    ),
    sortingField: 'estimated_monthly_savings',
    width: 130,
  },
];

function TagResourceTable({ tagValue, resources }) {
  return (
    <ExpandableSection
      variant="container"
      headerText={
        <SpaceBetween direction="horizontal" size="xs">
          <span>{tagValue}</span>
          <Badge>{resources.length} resource{resources.length !== 1 ? 's' : ''}</Badge>
        </SpaceBetween>
      }
    >
      <Table
        columnDefinitions={COLUMN_DEFINITIONS}
        items={resources.sort(
          (a, b) => (b.estimated_monthly_savings || 0) - (a.estimated_monthly_savings || 0)
        )}
        variant="embedded"
        stripedRows
        empty={
          <Box textAlign="center" color="inherit">
            No resources found
          </Box>
        }
      />
    </ExpandableSection>
  );
}

export default function ResourceDetails({ data }) {
  const { resources, tag_key } = data;

  if (!resources || Object.keys(resources).length === 0) {
    return null;
  }

  const tagValues = Object.keys(resources).sort();

  return (
    <Container
      header={
        <Header
          variant="h2"
          description="Detailed view of resources with optimization recommendations, grouped by tag value"
          counter={`(${tagValues.reduce((sum, tv) => sum + resources[tv].length, 0)} resources)`}
        >
          Resource Details
        </Header>
      }
    >
      <SpaceBetween size="m">
        {tagValues.map((tagValue) => (
          <TagResourceTable
            key={tagValue}
            tagValue={tagValue}
            resources={resources[tagValue]}
          />
        ))}
      </SpaceBetween>
    </Container>
  );
}
