import React from 'react';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import Table from '@cloudscape-design/components/table';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import ColumnLayout from '@cloudscape-design/components/column-layout';
import ProgressBar from '@cloudscape-design/components/progress-bar';
import StatusIndicator from '@cloudscape-design/components/status-indicator';

function formatCurrency(value) {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function getScoreStatus(score) {
  if (score === null || score === undefined) return 'stopped';
  if (score >= 90) return 'success';
  if (score >= 70) return 'warning';
  return 'error';
}

function getScoreLabel(score) {
  if (score === null || score === undefined) return 'N/A';
  if (score >= 90) return 'Optimized';
  if (score >= 70) return 'Needs attention';
  return 'Action required';
}

export default function EfficiencySummary({ data }) {
  const { results, totals, tag_key } = data;

  const columnDefinitions = [
    {
      id: 'tag_value',
      header: `Tag: ${tag_key}`,
      cell: (item) => <Box fontWeight="bold">{item.tag_value}</Box>,
      sortingField: 'tag_value',
      width: 200,
    },
    {
      id: 'efficiency_score',
      header: 'Efficiency score',
      cell: (item) => {
        if (item.efficiency_score === null) return '-';
        const status = getScoreStatus(item.efficiency_score);
        return (
          <ProgressBar
            value={item.efficiency_score}
            status={status === 'error' ? 'error' : 'in-progress'}
            resultText={`${item.efficiency_score.toFixed(1)}%`}
            additionalInfo={getScoreLabel(item.efficiency_score)}
          />
        );
      },
      sortingField: 'efficiency_score',
      width: 250,
    },
    {
      id: 'optimizable_spend',
      header: 'Optimizable spend',
      cell: (item) => formatCurrency(item.optimizable_spend),
      sortingField: 'optimizable_spend',
    },
    {
      id: 'potential_savings',
      header: 'Potential savings',
      cell: (item) => (
        <Box color="text-status-success" fontWeight="bold">
          {formatCurrency(item.potential_savings)}
        </Box>
      ),
      sortingField: 'potential_savings',
    },
  ];

  return (
    <SpaceBetween size="l">
      {/* Summary cards */}
      <Container>
        <ColumnLayout columns={4} variant="text-grid">
          <div>
            <Box variant="awsui-key-label">Overall Efficiency</Box>
            <Box variant="awsui-value-large">
              {totals.efficiency_score !== null
                ? `${totals.efficiency_score.toFixed(1)}%`
                : 'N/A'}
            </Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Total Optimizable Spend</Box>
            <Box variant="awsui-value-large">
              {formatCurrency(totals.optimizable_spend)}
            </Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Total Potential Savings</Box>
            <Box variant="awsui-value-large" color="text-status-success">
              {formatCurrency(totals.potential_savings)}
            </Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Tag Values Found</Box>
            <Box variant="awsui-value-large">{results.length}</Box>
          </div>
        </ColumnLayout>
      </Container>

      {/* Efficiency table */}
      <Table
        columnDefinitions={columnDefinitions}
        items={results}
        sortingDisabled={false}
        variant="container"
        header={
          <Header
            variant="h2"
            description="Cost efficiency score broken down by tag value"
            counter={`(${results.length})`}
          >
            Efficiency by Tag Value
          </Header>
        }
        footer={
          <Box textAlign="right" fontWeight="bold" padding={{ right: 'l' }}>
            Total: {formatCurrency(totals.optimizable_spend)} spend |{' '}
            {formatCurrency(totals.potential_savings)} savings |{' '}
            {totals.efficiency_score !== null
              ? `${totals.efficiency_score.toFixed(1)}% efficient`
              : 'N/A'}
          </Box>
        }
        empty={
          <Box textAlign="center" color="inherit">
            No results found
          </Box>
        }
      />
    </SpaceBetween>
  );
}
