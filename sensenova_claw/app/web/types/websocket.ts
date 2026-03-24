export interface WsMessage {
  type: string;
  session_id?: string;
  payload: Record<string, unknown>;
  timestamp: number;
}
