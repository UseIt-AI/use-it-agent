/**
 * AskUserCard
 *
 * Inline question card rendered inside the assistant message's block
 * stream. Styled to feel like a native part of the chat (Cursor / Claude
 * style), not a modal or an alert.
 *
 * Interaction model (two-step, explicit Confirm):
 *   1. User picks an option (or types into "Other") — this updates the
 *      card's visual "active selection" but does NOT settle anything.
 *   2. User clicks the **Confirm** button (or presses Enter) — this sends
 *      the final reply to the orchestrator.
 *
 * Kinds:
 *   - confirm      : single-select; `default_option_id` is pre-selected
 *                    so the user can just press Confirm.
 *   - choose       : single-select, one option per line.
 *   - multi_choose : multi-select with checkboxes; Confirm sends all
 *                    checked ids. "Other" is an optional add-on note.
 *   - input        : primarily free-text; any `options` become quick picks.
 *
 * "Other" row:
 *   If `allow_free_text === true` (or `kind === 'input'`), we render an
 *   "Other…" row after the options. Clicking expands it into an inline
 *   textarea. For `input` kind it's expanded from the start.
 *
 * No dismiss:
 *   The AI is waiting for an answer, so there's no user-facing dismiss
 *   button. Backend-provided `timeout_seconds > 0` still runs silently
 *   to prevent deadlocks in unattended flows.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Check, Pencil } from 'lucide-react';
import type { AskUserBlock } from '../handlers/types';
import type {
  AskUserOption,
  AskUserResponse,
} from '../handlers/localEngine/types';

interface AskUserCardProps {
  block: AskUserBlock;
  onSettle: (toolCallId: string, reply: AskUserResponse) => void;
}

/** The currently "active" pick — what Confirm will submit. */
type Active =
  | { kind: 'option'; id: string }
  | { kind: 'other' }
  | null;

function validDefault(
  id: string | null | undefined,
  options: AskUserOption[],
): string | null {
  if (!id) return null;
  return options.some((o) => o.id === id) ? id : null;
}

export const AskUserCard: React.FC<AskUserCardProps> = ({ block, onSettle }) => {
  const { args, status, answer, toolCallId } = block;
  const isPending = status === 'pending';
  const isAnswered = status === 'answered';

  const options = args.options || [];
  const isMulti = args.kind === 'multi_choose';
  const isInput = args.kind === 'input';
  const allowOther = isInput || args.allow_free_text;
  const defaultId = useMemo(
    () => validDefault(args.default_option_id ?? null, options),
    [args.default_option_id, options],
  );

  // ---- State ---------------------------------------------------------------
  // Single-select "active" pick.
  const [active, setActive] = useState<Active>(
    defaultId && !isMulti && !isInput ? { kind: 'option', id: defaultId } : null,
  );
  // Multi-select checked ids.
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [freeText, setFreeText] = useState('');
  const [otherOpen, setOtherOpen] = useState<boolean>(isInput);

  // Re-derive visible selections when the card becomes non-pending.
  const selectedInAnswer = useMemo(() => {
    if (!answer) return new Set<string>();
    if (answer.selected_option_ids?.length) {
      return new Set(answer.selected_option_ids);
    }
    if (answer.selected_option_id) {
      return new Set([answer.selected_option_id]);
    }
    return new Set<string>();
  }, [answer]);

  // Reset per-toolCallId (defensive; cards are 1:1 with a tool_call in practice).
  useEffect(() => {
    if (!isPending) return;
    setActive(
      defaultId && !isMulti && !isInput ? { kind: 'option', id: defaultId } : null,
    );
    setChecked(new Set<string>());
    setFreeText('');
    setOtherOpen(isInput);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toolCallId]);

  // Silent backend-driven timeout (no visible countdown).
  useEffect(() => {
    if (!isPending) return;
    const t = args.timeout_seconds;
    if (!t || t <= 0) return;
    const handle = setTimeout(() => {
      onSettle(toolCallId, {
        selected_option_id: null,
        selected_option_ids: [],
        free_text: '',
        dismissed: true,
      });
    }, t * 1000);
    return () => clearTimeout(handle);
  }, [isPending, args.timeout_seconds, toolCallId, onSettle]);

  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  useEffect(() => {
    if (!isPending || !otherOpen) return;
    const id = requestAnimationFrame(() => textareaRef.current?.focus());
    return () => cancelAnimationFrame(id);
  }, [isPending, otherOpen]);

  // ---- Derived: is Confirm enabled?  --------------------------------------
  const canConfirm = useMemo(() => {
    if (!isPending) return false;
    if (isMulti) {
      return checked.size > 0 || freeText.trim().length > 0;
    }
    if (active?.kind === 'option') return true;
    if (active?.kind === 'other') return freeText.trim().length > 0;
    // For input kind with no active yet, a non-empty textbox still counts.
    if (isInput && freeText.trim().length > 0) return true;
    return false;
  }, [isPending, isMulti, checked, active, freeText, isInput]);

  // ---- Handlers -----------------------------------------------------------
  const pickOption = (id: string) => {
    if (!isPending) return;
    if (isMulti) {
      setChecked((prev) => {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      });
    } else {
      setActive({ kind: 'option', id });
    }
  };

  const openOther = () => {
    if (!isPending) return;
    setOtherOpen(true);
    if (!isMulti) {
      setActive({ kind: 'other' });
    }
  };

  const onFreeTextChange = (v: string) => {
    setFreeText(v);
    // In single-select, typing in Other makes it the active choice.
    if (!isMulti && v.length > 0) {
      setActive({ kind: 'other' });
    }
  };

  const confirm = useCallback(() => {
    if (!isPending) return;
    const text = freeText.trim();

    if (isMulti) {
      if (checked.size === 0 && !text) return;
      const ids = Array.from(checked);
      onSettle(toolCallId, {
        selected_option_id: ids[0] ?? null,
        selected_option_ids: ids,
        free_text: text,
        dismissed: false,
      });
      return;
    }

    // Single-select / input
    if (active?.kind === 'option') {
      onSettle(toolCallId, {
        selected_option_id: active.id,
        selected_option_ids: [active.id],
        free_text: '',
        dismissed: false,
      });
      return;
    }

    if ((active?.kind === 'other' || isInput) && text) {
      onSettle(toolCallId, {
        selected_option_id: null,
        selected_option_ids: [],
        free_text: text,
        dismissed: false,
      });
      return;
    }
    // Otherwise nothing to confirm.
  }, [isPending, isMulti, checked, active, freeText, isInput, toolCallId, onSettle]);

  // Enter anywhere in the card = Confirm (if enabled). Handled here so
  // keyboard users don't need to tab to the button.
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!isPending) return;
    if (e.key === 'Enter' && !e.shiftKey && canConfirm) {
      // Allow default behavior inside the textarea only when Shift is held.
      e.preventDefault();
      confirm();
    }
  };

  // ---- Derived labels ------------------------------------------------------
  const answeredSummary = useMemo(() => {
    if (!answer || answer.dismissed) return '';
    const labels = options
      .filter((o) => selectedInAnswer.has(o.id))
      .map((o) => o.label);
    const text = answer.free_text?.trim() || '';
    if (labels.length && text) return `${labels.join('、')} — ${text}`;
    if (labels.length) return labels.join('、');
    return text;
  }, [answer, options, selectedInAnswer]);

  // ---- Visual --------------------------------------------------------------
  return (
    <div
      className="w-full max-w-[560px]"
      onKeyDown={onKeyDown}
      tabIndex={-1}
    >
      <p className="text-[14px] text-gray-900 leading-relaxed whitespace-pre-wrap break-words mb-2">
        {args.prompt}
      </p>

      {options.length > 0 && (
        <ul className="flex flex-col gap-1">
          {options.map((opt) => {
            const isChecked = isPending
              ? isMulti
                ? checked.has(opt.id)
                : active?.kind === 'option' && active.id === opt.id
              : selectedInAnswer.has(opt.id);

            return (
              <li key={opt.id}>
                <button
                  type="button"
                  disabled={!isPending}
                  onClick={() => pickOption(opt.id)}
                  aria-pressed={isChecked}
                  className={[
                    'group w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-left',
                    'text-[13.5px] transition-colors border',
                    isChecked
                      ? 'bg-gray-900/[0.03] border-gray-900/25 text-gray-900'
                      : 'bg-white border-gray-200 text-gray-700',
                    isPending
                      ? 'hover:bg-gray-50 hover:border-gray-300 cursor-pointer'
                      : 'cursor-default',
                    !isPending && !isChecked ? 'opacity-55' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                >
                  <Indicator isMulti={isMulti} isChecked={isChecked} />
                  <span className="flex-1 min-w-0 truncate">{opt.label}</span>
                </button>
              </li>
            );
          })}

          {allowOther && (
            <li>
              <OtherRow
                isPending={isPending}
                isOpen={otherOpen}
                isActive={!isMulti && active?.kind === 'other'}
                onOpen={openOther}
                onFocusRow={() => !isMulti && setActive({ kind: 'other' })}
                value={freeText}
                onChange={onFreeTextChange}
                answerFreeText={isAnswered ? answer?.free_text ?? '' : ''}
                textareaRef={textareaRef}
                isMulti={isMulti}
              />
            </li>
          )}
        </ul>
      )}

      {options.length === 0 && allowOther && (
        <OtherRow
          isPending={isPending}
          isOpen
          isActive
          onOpen={openOther}
          onFocusRow={() => !isMulti && setActive({ kind: 'other' })}
          value={freeText}
          onChange={onFreeTextChange}
          answerFreeText={isAnswered ? answer?.free_text ?? '' : ''}
          textareaRef={textareaRef}
          isMulti={false}
        />
      )}

      {/* Confirm bar */}
      {isPending && (
        <div className="mt-2.5 flex items-center justify-end gap-2">
          {isMulti && (
            <span className="text-[11px] text-gray-500">
              {checked.size > 0
                ? `${checked.size} selected`
                : 'Pick one or more'}
            </span>
          )}
          <button
            type="button"
            onClick={confirm}
            disabled={!canConfirm}
            className={[
              'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md',
              'text-[12px] font-medium transition-colors',
              canConfirm
                ? 'bg-gray-900 text-white hover:bg-black'
                : 'bg-gray-200 text-gray-400 cursor-not-allowed',
            ].join(' ')}
          >
            <span>Confirm</span>
            <span
              className={[
                'text-[10px] px-1 py-px rounded border',
                canConfirm
                  ? 'border-white/20 text-white/80'
                  : 'border-gray-300 text-gray-400',
              ].join(' ')}
            >
              ↵
            </span>
          </button>
        </div>
      )}

      {isAnswered && answeredSummary && (
        <div className="mt-1.5 text-[11px] text-gray-400 inline-flex items-center gap-1">
          <Check className="w-3 h-3" strokeWidth={2.5} />
          <span className="truncate max-w-[520px]">Replied: {answeredSummary}</span>
        </div>
      )}
    </div>
  );
};

// ---- Radio / checkbox indicator -------------------------------------------
const Indicator: React.FC<{ isMulti: boolean; isChecked: boolean }> = ({
  isMulti,
  isChecked,
}) => (
  <span
    aria-hidden
    className={[
      'flex-shrink-0 w-3.5 h-3.5 flex items-center justify-center transition-colors',
      isMulti ? 'rounded-[4px] border' : 'rounded-full border',
      isChecked
        ? 'bg-gray-900 border-gray-900 text-white'
        : 'bg-white border-gray-300',
    ].join(' ')}
  >
    {isMulti
      ? isChecked && <Check className="w-2.5 h-2.5" strokeWidth={3.5} />
      : isChecked && <span className="w-1.5 h-1.5 rounded-full bg-white" />}
  </span>
);

// ---- "Other" row ----------------------------------------------------------
interface OtherRowProps {
  isPending: boolean;
  isOpen: boolean;
  /** Whether this row is the "active" pick in single-select mode. */
  isActive: boolean;
  onOpen: () => void;
  onFocusRow: () => void;
  value: string;
  onChange: (v: string) => void;
  answerFreeText: string;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  isMulti: boolean;
}

const OtherRow: React.FC<OtherRowProps> = ({
  isPending,
  isOpen,
  isActive,
  onOpen,
  onFocusRow,
  value,
  onChange,
  answerFreeText,
  textareaRef,
  isMulti,
}) => {
  if (!isPending) {
    if (!answerFreeText.trim()) return null;
    return (
      <div className="flex items-start gap-2 px-3 py-2 rounded-lg border border-gray-200 bg-white text-[13.5px] text-gray-800">
        <Pencil className="w-3.5 h-3.5 text-gray-400 mt-0.5 flex-shrink-0" />
        <span className="flex-1 whitespace-pre-wrap break-words">
          {answerFreeText}
        </span>
      </div>
    );
  }

  if (!isOpen) {
    return (
      <button
        type="button"
        onClick={onOpen}
        className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg border border-dashed border-gray-300 text-[13.5px] text-gray-500 hover:bg-gray-50 hover:text-gray-700 hover:border-gray-400 transition-colors text-left"
      >
        <Pencil className="w-3.5 h-3.5 flex-shrink-0" />
        <span>Other… (type your own answer)</span>
      </button>
    );
  }

  const activeBorder =
    !isMulti && isActive
      ? 'border-gray-900/25 bg-gray-900/[0.03]'
      : 'border-gray-300 bg-white';

  return (
    <div
      className={[
        'flex items-start gap-2 px-3 py-2 rounded-lg border transition-colors',
        activeBorder,
        'focus-within:border-gray-900/40 focus-within:ring-2 focus-within:ring-gray-900/5',
      ].join(' ')}
      onClick={onFocusRow}
    >
      <Pencil className="w-3.5 h-3.5 text-gray-400 mt-1 flex-shrink-0" />
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={onFocusRow}
        rows={1}
        placeholder={isMulti ? 'Add a note (optional)…' : 'Type your answer…'}
        className="flex-1 resize-none bg-transparent text-[13.5px] text-gray-900 placeholder:text-gray-400 focus:outline-none leading-5 min-h-[20px] max-h-[120px]"
        onInput={(e) => {
          const el = e.currentTarget;
          el.style.height = 'auto';
          el.style.height = Math.min(el.scrollHeight, 120) + 'px';
        }}
      />
    </div>
  );
};

export default AskUserCard;
