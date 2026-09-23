import { useMutation } from "@tanstack/react-query";
import { sendChatMessage } from "../api/assistant";

export function useSendChatMessage() {
  return useMutation({
    mutationFn: (params: { session_id?: number | null; message: string }) => sendChatMessage(params),
  });
}
