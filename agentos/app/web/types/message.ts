export type MessageRole = 'user' | 'assistant' | 'tool' | 'system';

export interface ToolInfo {
  name: string;
  arguments: Record<string, any>;
  result?: any;
  success?: boolean;
  error?: string;
  status: 'running' | 'completed';
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: number;
  toolInfo?: ToolInfo;
}
