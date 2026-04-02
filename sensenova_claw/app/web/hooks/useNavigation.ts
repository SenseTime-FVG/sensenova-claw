'use client';

import { useMemo } from 'react';
import { usePathname } from 'next/navigation';
import { useFeatureNavItems, useAdminNavItems, type SubNavGroup } from '@/components/layout/DashboardNav';

export function useNavigation(manualGroup: SubNavGroup = null) {
  const pathname = usePathname();
  const featureNavItems = useFeatureNavItems();
  const adminNavItems = useAdminNavItems();

  const isFeatureActive = useMemo(() => 
    featureNavItems.some((item) => pathname?.startsWith(item.path)),
    [featureNavItems, pathname]
  );

  const isAdminActive = useMemo(() => 
    adminNavItems.some((item) => pathname?.startsWith(item.path)),
    [adminNavItems, pathname]
  );

  const visibleGroup: SubNavGroup = useMemo(() => {
    if (manualGroup) return manualGroup;
    if (isFeatureActive) return 'features';
    if (isAdminActive) return 'admin';
    return null;
  }, [manualGroup, isFeatureActive, isAdminActive]);

  const subNavItems = useMemo(() => {
    if (visibleGroup === 'features') return featureNavItems;
    if (visibleGroup === 'admin') return adminNavItems;
    return null;
  }, [visibleGroup, featureNavItems]);

  return {
    pathname,
    visibleGroup,
    subNavItems,
    isFeatureActive,
    isAdminActive,
  };
}
