import React, { useState, useCallback } from 'react';
import AppLayout from '@cloudscape-design/components/app-layout';
import ContentLayout from '@cloudscape-design/components/content-layout';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import TopNavigation from '@cloudscape-design/components/top-navigation';
import FilterPanel from './components/FilterPanel';
import EfficiencySummary from './components/EfficiencySummary';
import ResourceDetails from './components/ResourceDetails';

export default function App() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = useCallback(async (filters) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set('tag_key', filters.tagKey);
      if (filters.tagValue) params.set('tag_value', filters.tagValue);
      params.set('show_resources', 'true');

      const response = await fetch(`/api/efficiency?${params.toString()}`);
      if (!response.ok) {
        const errBody = await response.json().catch(() => ({}));
        throw new Error(errBody.detail || `Request failed with status ${response.status}`);
      }
      const result = await response.json();
      setData(result);
    } catch (err) {
      setError(err.message);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <>
      <TopNavigation
        identity={{
          href: '/',
          title: 'Cost Optimization Hub',
        }}
        utilities={[
          {
            type: 'button',
            text: 'AWS Documentation',
            href: 'https://docs.aws.amazon.com/cost-management/latest/userguide/coh-cost-efficiency.html',
            external: true,
            externalIconAriaLabel: '(opens in a new tab)',
          },
        ]}
      />
      <AppLayout
        content={
          <ContentLayout
            header={
              <Header
                variant="h1"
                description="Calculate and visualize Cost Efficiency Scores grouped by resource tags. Identify optimization opportunities per application, team, or environment."
              >
                Cost Efficiency Score by Tag
              </Header>
            }
          >
            <SpaceBetween size="l">
              <FilterPanel onSubmit={handleSubmit} loading={loading} />
              {error && (
                <div style={{ color: '#d91515', padding: '12px', background: '#fdf3f3', borderRadius: '8px' }}>
                  Error: {error}
                </div>
              )}
              {data && <EfficiencySummary data={data} />}
              {data && data.resources && <ResourceDetails data={data} />}
            </SpaceBetween>
          </ContentLayout>
        }
        navigationHide
        toolsHide
      />
    </>
  );
}
