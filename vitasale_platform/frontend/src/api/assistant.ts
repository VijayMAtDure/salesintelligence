import { apiClient } from "./client";

export interface ConversationMessage {
  id: number;
  role: "user" | "assistant" | "tool";
  content: string;
  tool_name: string;
  created_at: string;
}

export interface ChatResponse {
  session_id: number;
  reply: string;
  messages: ConversationMessage[];
}

export async function sendChatMessage(params: {
  session_id?: number | null;
  message: string;
}): Promise<ChatResponse> {
  return (await apiClient.post<ChatResponse>("/assistant/chat/", params)).data;
}
