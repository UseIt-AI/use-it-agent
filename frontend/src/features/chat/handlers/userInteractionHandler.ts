/**
 * User Interaction Handler
 *
 * Handles `tool_call` events whose `target === "user"`. The Orchestrator
 * pauses its loop and expects the frontend to:
 *
 *   1. Render the question INLINE in the current assistant message
 *      (as an `AskUserBlock`) — so the Q&A becomes part of the chat
 *      history, just like a coding agent's prompt bubble.
 *   2. Wait for the user to click an option / submit text / dismiss.
 *   3. POST the user's reply back to the existing orchestrator callback
 *      endpoint, using the spec-defined `execution_result.user_response`
 *      nested body.
 *
 * The card's local state lives in `AskUserBlock` inside the message; the
 * resolver (promise) is held in `useAskUserStore`. When the user acts,
 * the card updates its block AND calls `settle(toolCallId, reply)` which
 * unblocks the promise here.
 */

import type React from 'react';
import { API_URL } from '@/config/runtimeEnv';
import { logRouter } from '@/utils/logger';
import { useAskUserStore } from '@/stores/useAskUserStore';
import type { Message } from './types';
import type {
  AskUserArgs,
  AskUserKind,
  AskUserOption,
  AskUserResponse,
  AskUserToolCallEvent,
} from './localEngine/types';

const CALLBACK_MAX_RETRIES = 3;
const CALLBACK_RETRY_DELAY_MS = 2000;

/**
 * Best-effort normalization of the tool_call args. Backend already
 * normalizes, but we defend against missing/malformed fields because the
 * SSE wire format is untyped JSON.
 */
function normalizeAskUserArgs(raw: any): AskUserArgs {
  const rawKind = typeof raw?.kind === 'string' ? raw.kind : 'confirm';
  const kind: AskUserKind =
    rawKind === 'choose' ||
    rawKind === 'input' ||
    rawKind === 'multi_choose'
      ? rawKind
      : 'confirm';

  const options: AskUserOption[] = Array.isArray(raw?.options)
    ? raw.options
        .filter((o: any) => o && typeof o.id === 'string' && o.id.length > 0)
        .map((o: any) => ({
          id: String(o.id),
          label: typeof o.label === 'string' && o.label ? o.label : String(o.id),
        }))
    : [];

  const defaultRaw = raw?.default_option_id;
  const default_option_id =
    typeof defaultRaw === 'string' && options.some((o) => o.id === defaultRaw)
      ? defaultRaw
      : null;

  const timeout = Number(raw?.timeout_seconds);
  const timeout_seconds = Number.isFinite(timeout) && timeout > 0 ? Math.floor(timeout) : 0;

  // `allow_free_text` is backend-controlled for confirm/choose/multi_choose
  // but must be true for `input`.
  const allow_free_text =
    kind === 'input' ? true : Boolean(raw?.allow_free_text);

  return {
    prompt: typeof raw?.prompt === 'string' ? raw.prompt : '',
    kind,
    options,
    default_option_id,
    allow_free_text,
    timeout_seconds,
  };
}

/**
 * POST the user's reply back to the orchestrator. Uses the same callback
 * endpoint as app-action tool_calls (no new endpoint per spec) but sends
 * the spec-defined `execution_result.user_response` nested body shape.
 * Also mirrors the top-level fields for back-compat.
 */
async function postUserResponseCallback(
  toolCallId: string,
  reply: AskUserResponse,
): Promise<void> {
  const body = {
    execution_result: {
      success: !reply.dismissed,
      tool_call_id: toolCallId,
      user_response: reply,
      // Back-compat fallback per spec § "Back-compat fallback".
      selected_option_id: reply.selected_option_id,
      selected_option_ids: reply.selected_option_ids,
      free_text: reply.free_text,
      dismissed: reply.dismissed,
    },
    status: reply.dismissed ? 'dismissed' : 'success',
    result: reply,
    error: null as string | null,
  };
  const payload = JSON.stringify(body);

  for (let attempt = 0; attempt < CALLBACK_MAX_RETRIES; attempt++) {
    try {
      const resp = await fetch(
        `${API_URL}/api/v1/workflow/callback/${toolCallId}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload,
        },
      );
      if (resp.ok) return;
      if (resp.status === 404 && attempt < CALLBACK_MAX_RETRIES - 1) {
        logRouter(
          '[AskUser] callback 404, retry %d/%d (id=%s)',
          attempt + 1,
          CALLBACK_MAX_RETRIES,
          toolCallId,
        );
        await new Promise((r) => setTimeout(r, CALLBACK_RETRY_DELAY_MS));
        continue;
      }
      // eslint-disable-next-line no-console
      console.warn(
        `[AskUser] callback non-ok: status=${resp.status}, id=${toolCallId}`,
      );
      return;
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error(
        `[AskUser] callback fetch error (attempt ${attempt + 1}):`,
        err,
      );
      if (attempt < CALLBACK_MAX_RETRIES - 1) {
        await new Promise((r) => setTimeout(r, CALLBACK_RETRY_DELAY_MS));
      }
    }
  }
}

export interface AskUserHandlerContext {
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  /** ID of the assistant message we should graft the block onto. */
  botMessageId: string;
}

/**
 * Append an `AskUserBlock` to the assistant message's `blocks` array.
 * If the bot message doesn't exist (e.g. the frontend is in a weird
 * mid-stream state), we fall back to creating a fresh one.
 */
function injectAskUserBlock(
  ctx: AskUserHandlerContext,
  toolCallId: string,
  args: AskUserArgs,
): void {
  const { setMessages, botMessageId } = ctx;
  const startedAt = Date.now();

  setMessages((prev) => {
    const idx = prev.findIndex((m) => m.id === botMessageId);
    const block = {
      type: 'ask_user' as const,
      toolCallId,
      args,
      status: 'pending' as const,
      startedAt,
    };

    if (idx < 0) {
      return [
        ...prev,
        {
          id: botMessageId,
          role: 'assistant' as const,
          timestamp: startedAt,
          blocks: [block],
        },
      ];
    }

    const msg = prev[idx];
    const blocks = [...(msg.blocks || []), block];
    const next = [...prev];
    next[idx] = { ...msg, blocks };
    return next;
  });
}

/**
 * Main entry. Called from the tool_call router when `target === "user"`.
 * Injects the inline card, waits for the user's reply, then POSTs it back.
 */
export async function handleAskUserCall(
  event: AskUserToolCallEvent,
  ctx: AskUserHandlerContext,
): Promise<void> {
  const { id, args } = event;
  const normalized = normalizeAskUserArgs(args);

  logRouter(
    '[AskUser] inline card: id=%s kind=%s options=%d timeout=%d',
    id,
    normalized.kind,
    normalized.options.length,
    normalized.timeout_seconds,
  );

  injectAskUserBlock(ctx, id, normalized);

  const reply = await new Promise<AskUserResponse>((resolve) => {
    useAskUserStore.getState().register(id, resolve);
  });

  logRouter(
    '[AskUser] settled: id=%s dismissed=%s selected=%s ids=%d textLen=%d',
    id,
    reply.dismissed,
    reply.selected_option_id,
    reply.selected_option_ids?.length ?? 0,
    reply.free_text?.length ?? 0,
  );

  await postUserResponseCallback(id, reply);
}
