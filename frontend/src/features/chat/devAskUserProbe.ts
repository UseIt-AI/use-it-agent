/**
 * Dev-only probe for the inline ask_user card.
 *
 * Exposes `window.__askUserTest(kind?, opts?)` so you can smoke-test the
 * card from DevTools without involving the backend. For that to work,
 * the probe needs somewhere to inject the `AskUserBlock` — normally this
 * comes from `useChat`'s currently-active assistant message. See
 * `runAskUserProbe(kind, ctx)` below; the chat input handler wires it up
 * when it detects a `/ask …` slash command.
 *
 *     /ask               -> confirm
 *     /ask choose        -> 4 single-select options
 *     /ask multi         -> 4 multi-select options
 *     /ask input         -> textbox + quick picks
 *     /ask timeout       -> 10s auto-dismiss
 */

import type React from 'react';
import type { Message } from '@/features/chat/handlers/types';
import { useAskUserStore } from '@/stores/useAskUserStore';
import type {
  AskUserArgs,
  AskUserResponse,
} from '@/features/chat/handlers/localEngine/types';

type ProbeKind = 'confirm' | 'choose' | 'multi' | 'input' | 'timeout';

const PRESETS: Record<ProbeKind, AskUserArgs> = {
  confirm: {
    prompt: '【本地测试】是否切换到"截图秒变 PPT"工作流？（不调用后端）',
    kind: 'confirm',
    options: [
      { id: 'run', label: '是的，立即运行' },
      { id: 'cancel', label: '先不运行' },
    ],
    default_option_id: 'run',
    allow_free_text: true,
    timeout_seconds: 0,
  },
  choose: {
    prompt: '【本地测试】布局检查发现 3 处重叠，你想怎么处理？',
    kind: 'choose',
    options: [
      { id: 'fix', label: '用 ppt_update_element 自动修复' },
      { id: 'skip', label: '先放着不管，我自己检查' },
      { id: 'resize', label: '把 slide 1 重新排版' },
      { id: 'abort', label: '停止任务' },
    ],
    default_option_id: 'fix',
    allow_free_text: true,
    timeout_seconds: 0,
  },
  multi: {
    prompt: '【本地测试】请选择要导出的章节（可多选）',
    kind: 'multi_choose',
    options: [
      { id: 'ch1', label: '第 1 章：背景介绍' },
      { id: 'ch2', label: '第 2 章：市场分析' },
      { id: 'ch3', label: '第 3 章：产品蓝图' },
      { id: 'ch4', label: '第 4 章：关键数据' },
    ],
    default_option_id: null,
    allow_free_text: true,
    timeout_seconds: 0,
  },
  input: {
    prompt: '【本地测试】请给这页 PPT 起一个标题（可选候选或自由输入）',
    kind: 'input',
    options: [
      { id: 'intro', label: '公司介绍' },
      { id: 'roadmap', label: '产品路线图' },
      { id: 'numbers', label: '关键数据' },
    ],
    default_option_id: null,
    allow_free_text: true,
    timeout_seconds: 0,
  },
  timeout: {
    prompt: '【本地测试】10 秒内不回答就会被自动判作 dismissed。',
    kind: 'confirm',
    options: [
      { id: 'yes', label: '我在' },
      { id: 'no', label: '不在' },
    ],
    default_option_id: 'yes',
    allow_free_text: false,
    timeout_seconds: 10,
  },
};

function genId() {
  return 'probe_' + Math.random().toString(36).slice(2, 10);
}

export interface AskUserProbeContext {
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  /** ID of the assistant message that should host the ask_user block. */
  botMessageId: string;
}

/**
 * Fire a local ask_user flow that mirrors the real handler, but skips the
 * HTTP callback. Returns the reply so you can inspect what a real callback
 * body would carry.
 */
export async function runAskUserProbe(
  kind: ProbeKind,
  ctx: AskUserProbeContext,
): Promise<AskUserResponse> {
  const args = PRESETS[kind] ?? PRESETS.confirm;
  const id = genId();
  const startedAt = Date.now();

  // Inject the inline block on the assistant message.
  ctx.setMessages((prev) => {
    const idx = prev.findIndex((m) => m.id === ctx.botMessageId);
    const block = {
      type: 'ask_user' as const,
      toolCallId: id,
      args,
      status: 'pending' as const,
      startedAt,
    };
    if (idx < 0) {
      return [
        ...prev,
        {
          id: ctx.botMessageId,
          role: 'assistant' as const,
          timestamp: startedAt,
          blocks: [block],
        },
      ];
    }
    const msg = prev[idx];
    const next = [...prev];
    next[idx] = { ...msg, blocks: [...(msg.blocks || []), block] };
    return next;
  });

  const reply = await new Promise<AskUserResponse>((resolve) => {
    useAskUserStore.getState().register(id, resolve);
  });

  // eslint-disable-next-line no-console
  console.log('[AskUserProbe] reply id=%s %o', id, reply);
  return reply;
}

/**
 * Recognise a slash command in a chat message. Returns the probe kind if
 * the message matches, otherwise null.
 */
export function parseAskProbeCommand(message: string): ProbeKind | null {
  const m = message.trim().match(/^\/ask(?:\s+(\w+))?\s*$/i);
  if (!m) return null;
  const raw = (m[1] || 'confirm').toLowerCase();
  const alias: Record<string, ProbeKind> = {
    confirm: 'confirm',
    choose: 'choose',
    single: 'choose',
    multi: 'multi',
    multiple: 'multi',
    multi_choose: 'multi',
    input: 'input',
    text: 'input',
    timeout: 'timeout',
  };
  return alias[raw] ?? 'confirm';
}

// Banner only — actual probe now requires a setMessages/botMessageId
// context, so window.__askUserTest only prints guidance.
if (typeof window !== 'undefined') {
  (window as any).__askUserTest = () => {
    // eslint-disable-next-line no-console
    console.warn(
      '[AskUserProbe] Type "/ask", "/ask choose", "/ask multi", "/ask input", or "/ask timeout" in the chat input to trigger the inline card. (The old window.__askUserTest modal has been removed.)',
    );
  };
  // eslint-disable-next-line no-console
  console.log(
    '[AskUserProbe] Ready. In chat input, type:\n' +
      '  /ask               -> confirm\n' +
      '  /ask choose        -> single-select (4 options)\n' +
      '  /ask multi         -> multi-select (4 options)\n' +
      '  /ask input         -> textbox + quick picks\n' +
      '  /ask timeout       -> 10s auto-dismiss',
  );
}
