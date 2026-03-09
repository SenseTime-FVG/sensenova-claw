export interface Session {
  session_id: string;
  created_at: number;
  last_active: number;
  meta?: {
    title?: string;
    model?: string;
  };
}
