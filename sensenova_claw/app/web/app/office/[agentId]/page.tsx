'use client';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { OfficeShell } from '@/components/office/OfficeShell';

export default function AgentOfficePage({
  params,
}: {
  params: { agentId: string };
}) {
  return (
    <DashboardLayout>
      <OfficeShell selectedAgentId={params.agentId} />
    </DashboardLayout>
  );
}
