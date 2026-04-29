interface ChatHistoryItem {
  id: string;
  title: string;
  projectId: string;
  projectName?: string;
  messageCount: number;
  lastMessageAt: string;
  lastMessagePreview?: string;
  createdAt: string;
  updatedAt: string;
}
