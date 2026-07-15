import React, { useState } from 'react';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import FormField from '@cloudscape-design/components/form-field';
import Input from '@cloudscape-design/components/input';
import Button from '@cloudscape-design/components/button';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Grid from '@cloudscape-design/components/grid';
import Alert from '@cloudscape-design/components/alert';

export default function FilterPanel({ onSubmit, loading }) {
  const [tagKey, setTagKey] = useState('');
  const [tagValue, setTagValue] = useState('');
  const [tagKeyError, setTagKeyError] = useState('');

  const handleSubmit = () => {
    if (!tagKey.trim()) {
      setTagKeyError('Tag key is required.');
      return;
    }
    setTagKeyError('');
    onSubmit({
      tagKey: tagKey.trim(),
      tagValue: tagValue.trim() || null,
    });
  };

  return (
    <Container
      header={<Header variant="h2">Query Parameters</Header>}
    >
      <SpaceBetween size="l">
        <Alert statusIconAriaLabel="Info" type="info">
          Efficiency scores use a rolling 30-day spend window, matching the AWS Cost Optimization Hub console.
          Resources must be tagged with active cost allocation tags.
        </Alert>
        <Grid
          gridDefinition={[
            { colspan: { default: 12, m: 6 } },
            { colspan: { default: 12, m: 6 } },
          ]}
        >
          <FormField
            label="Tag key"
            description="The AWS resource tag key to group by (e.g. Application, Team)"
            errorText={tagKeyError}
          >
            <Input
              value={tagKey}
              onChange={({ detail }) => {
                setTagKey(detail.value);
                if (detail.value.trim()) setTagKeyError('');
              }}
              placeholder="e.g. Application"
              disabled={loading}
            />
          </FormField>

          <FormField
            label={<span>Tag value <i>- optional</i></span>}
            description="Filter to a specific tag value, or leave empty for all values"
          >
            <Input
              value={tagValue}
              onChange={({ detail }) => setTagValue(detail.value)}
              placeholder="e.g. PaymentService"
              disabled={loading}
            />
          </FormField>
        </Grid>

        <Button
          variant="primary"
          onClick={handleSubmit}
          loading={loading}
          loadingText="Calculating..."
          iconName="search"
        >
          Calculate Efficiency Score
        </Button>
      </SpaceBetween>
    </Container>
  );
}
