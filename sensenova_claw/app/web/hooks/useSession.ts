'use client';

import { useSessionContext } from '@/contexts/SessionContext';

export function useSession() {
  return useSessionContext();
}
