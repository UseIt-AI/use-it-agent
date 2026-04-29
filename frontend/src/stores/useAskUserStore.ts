/**
 * Ask User Store
 *
 * Coordinates the Orchestrator's `ask_user` tool_call with the inline
 * chat card that actually captures the answer.
 *
 *   handler: registers a resolver for `toolCallId` and awaits it
 *            (see `features/chat/handlers/userInteractionHandler.ts`)
 *   card:    calls `settle(toolCallId, reply)` when the user picks an
 *            option / submits text / dismisses / times out
 *            (see `features/chat/components/AskUserCard.tsx`)
 *
 * The actual question / options / status lives INSIDE the chat message as
 * an `AskUserBlock` — not here — so it becomes part of the conversation
 * history like a normal bubble.
 */

import { create } from 'zustand';
import type { AskUserResponse } from '@/features/chat/handlers/localEngine/types';

type Resolver = (reply: AskUserResponse) => void;

interface AskUserState {
  /**
   * Pending resolvers keyed by tool_call id. When the user answers in
   * the inline card we look the resolver up by id and unblock the handler.
   */
  resolvers: Map<string, Resolver>;

  /** Register a resolver so the card can settle us later. */
  register: (toolCallId: string, resolve: Resolver) => void;

  /**
   * Resolve the pending request with the user's reply. No-op if the id
   * is unknown (e.g. the handler has already timed out server-side).
   */
  settle: (toolCallId: string, reply: AskUserResponse) => void;

  /** Returns true if a card still has a live resolver (i.e. still pending). */
  isPending: (toolCallId: string) => boolean;
}

export const useAskUserStore = create<AskUserState>()((set, get) => ({
  resolvers: new Map(),

  register: (toolCallId, resolve) => {
    const next = new Map(get().resolvers);
    const prev = next.get(toolCallId);
    if (prev) {
      try {
        prev({
          selected_option_id: null,
          selected_option_ids: [],
          free_text: '',
          dismissed: true,
        });
      } catch {
        // ignore
      }
    }
    next.set(toolCallId, resolve);
    set({ resolvers: next });
  },

  settle: (toolCallId, reply) => {
    const current = get().resolvers;
    const resolver = current.get(toolCallId);
    if (!resolver) return;
    try {
      resolver(reply);
    } finally {
      const next = new Map(current);
      next.delete(toolCallId);
      set({ resolvers: next });
    }
  },

  isPending: (toolCallId) => get().resolvers.has(toolCallId),
}));
