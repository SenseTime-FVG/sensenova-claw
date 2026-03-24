'use client';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { OfficeView } from '@/components/office/OfficeView';

export default function OfficePage() {
  return (
    <DashboardLayout>
      <OfficeView />
    </DashboardLayout>
  );
}
