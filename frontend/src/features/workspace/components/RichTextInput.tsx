import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useEditor, EditorContent, NodeViewWrapper, ReactNodeViewRenderer } from '@tiptap/react';
import type { ReactNodeViewProps } from '@tiptap/react';
import type { Editor } from '@tiptap/core';
import { Node, mergeAttributes } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import { File as FileIcon, X, ChevronDown } from 'lucide-react';
import { parseQuickStartMessage } from '@/features/workflow/utils/quickStartParser';
import { flattenAllFiles } from '@/features/chat/utils/fileTreeUtils';
import type { FlatFileItem } from '@/features/chat/utils/fileTreeUtils';
import type { FileNode } from '@/features/workspace/file-explorer/types';
import type { JSONContent } from '@tiptap/core';

// ── Context for passing callbacks and data into node views ──────────────────

interface FileMentionContextValue {
  onRemove: (name: string) => void;
  onReplace: (oldName: string, newFile: FlatFileItem) => void;
  allFiles: FlatFileItem[];
}

const FileMentionContext = createContext<FileMentionContextValue | null>(null);

// ── FileMention Node Extension ──────────────────────────────────────────────

function getFileExtension(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot >= 0 ? name.slice(dot).toLowerCase() : '';
}

const FileMentionComponent = ({ node, deleteNode, updateAttributes }: ReactNodeViewProps) => {
  const ctx = useContext(FileMentionContext);
  const [showReplace, setShowReplace] = useState(false);
  const [ddPos, setDdPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const dropdownRef = useRef<HTMLDivElement>(null);
  const tagRef = useRef<HTMLSpanElement>(null);

  const ext = getFileExtension(node.attrs.name);
  const alternatives = useMemo(() => {
    if (!ctx) return [];
    return ctx.allFiles.filter(f => getFileExtension(f.name) === ext && f.name !== node.attrs.name);
  }, [ctx, ext, node.attrs.name]);

  const handleRemove = () => {
    ctx?.onRemove(node.attrs.name);
    deleteNode();
  };

  const handleReplace = (file: FlatFileItem) => {
    ctx?.onReplace(node.attrs.name, file);
    updateAttributes({ path: file.path, name: file.name });
    setShowReplace(false);
  };

  const hoverTimeout = useRef<ReturnType<typeof setTimeout>>();

  const openDropdown = () => {
    if (tagRef.current) {
      const rect = tagRef.current.getBoundingClientRect();
      setDdPos({ top: rect.bottom + 4, left: rect.left });
    }
    setShowReplace(true);
  };

  const handleBtnEnter = () => {
    clearTimeout(hoverTimeout.current);
    openDropdown();
  };

  const handleLeave = () => {
    hoverTimeout.current = setTimeout(() => setShowReplace(false), 150);
  };

  const handleDropdownEnter = () => {
    clearTimeout(hoverTimeout.current);
  };

  // Adjust if overflowing viewport
  useEffect(() => {
    if (!showReplace || !dropdownRef.current) return;
    const el = dropdownRef.current;
    const rect = el.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let { top, left } = ddPos;
    if (rect.right > vw - 8) left = Math.max(8, vw - rect.width - 8);
    if (rect.bottom > vh - 8) top = ddPos.top - rect.height - (tagRef.current?.getBoundingClientRect().height ?? 20) - 8;
    if (left !== ddPos.left || top !== ddPos.top) {
      setDdPos({ top, left });
    }
  }, [showReplace, ddPos]);

  return (
    <NodeViewWrapper as="span" className="inline-flex align-baseline mx-0.5">
      <span
        ref={tagRef}
        className="group/mention inline-flex items-center gap-1 px-1.5 py-0.5 bg-orange-50/80 border border-orange-200/60 rounded text-[11px] text-orange-800 font-medium select-none cursor-pointer"
      >
        <FileIcon className="w-2.5 h-2.5 flex-shrink-0" />
        {node.attrs.name}
        {alternatives.length > 0 && (
          <button
            type="button"
            onMouseEnter={handleBtnEnter}
            onMouseLeave={handleLeave}
            className="opacity-0 group-hover/mention:opacity-100 transition-opacity p-0.5 hover:bg-orange-200 rounded-sm flex-shrink-0"
            contentEditable={false}
          >
            <ChevronDown className="w-2.5 h-2.5 text-orange-700" />
          </button>
        )}
        <button
          type="button"
          onClick={handleRemove}
          className="opacity-0 group-hover/mention:opacity-100 transition-opacity p-0.5 hover:bg-orange-200 rounded-sm flex-shrink-0 -mr-0.5"
          contentEditable={false}
        >
          <X className="w-2.5 h-2.5 text-orange-700" />
        </button>
      </span>
      {showReplace && alternatives.length > 0 && (
        <div
          ref={dropdownRef}
          onMouseEnter={handleDropdownEnter}
          onMouseLeave={handleLeave}
          className="fixed w-[240px] max-h-[200px] overflow-y-auto bg-white border border-gray-200 rounded-lg shadow-lg z-[9999]"
          style={{ top: ddPos.top, left: ddPos.left }}
          contentEditable={false}
        >
          <div className="py-1">
            <div className="px-2.5 py-1 text-[10px] text-black/40 font-medium uppercase tracking-wider">
              Replace with
            </div>
            {alternatives.map(file => (
              <button
                key={file.path}
                type="button"
                onClick={() => handleReplace(file)}
                className="w-full flex items-center gap-1.5 px-2.5 py-1.5 text-left text-xs text-gray-700 hover:bg-orange-50 hover:text-orange-900 transition-colors"
              >
                <FileIcon className="w-3 h-3 flex-shrink-0 text-gray-400" />
                <span className="font-medium truncate">{file.name}</span>
                <span className="text-[10px] text-black/25 truncate ml-auto max-w-[40%]">
                  {file.relativePath}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </NodeViewWrapper>
  );
};

const FileMention = Node.create({
  name: 'fileMention',
  group: 'inline',
  inline: true,
  atom: true,

  addAttributes() {
    return {
      path: { default: '' },
      name: { default: '' },
    };
  },

  parseHTML() {
    return [{ tag: 'span[data-file-mention]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return ['span', mergeAttributes({ 'data-file-mention': '' }, HTMLAttributes), HTMLAttributes.name || ''];
  },

  addNodeView() {
    return ReactNodeViewRenderer(FileMentionComponent);
  },
});

// ── Helpers: convert between plain text (with @file refs) and TipTap JSON ───

function textToTiptapContent(text: string): JSONContent {
  if (!text) {
    return { type: 'doc', content: [{ type: 'paragraph' }] };
  }

  const lines = text.split('\n');
  const paragraphs: JSONContent[] = lines.map(line => {
    const segments = parseQuickStartMessage(line);
    if (segments.length === 0) {
      return { type: 'paragraph' };
    }

    const content: JSONContent[] = [];
    for (const seg of segments) {
      if (seg.type === 'text') {
        if (seg.value) content.push({ type: 'text', text: seg.value });
      } else {
        content.push({
          type: 'fileMention',
          attrs: { path: seg.path, name: seg.name },
        });
      }
    }
    return { type: 'paragraph', content: content.length > 0 ? content : undefined };
  });

  return { type: 'doc', content: paragraphs };
}

function extractMentionNames(doc: JSONContent): Set<string> {
  const names = new Set<string>();
  if (!doc.content) return names;
  for (const para of doc.content) {
    if (!para.content) continue;
    for (const node of para.content) {
      if (node.type === 'fileMention' && node.attrs?.name) {
        names.add(node.attrs.name);
      }
    }
  }
  return names;
}

function tiptapContentToText(doc: JSONContent): string {
  if (!doc.content) return '';

  return doc.content.map(paragraph => {
    if (!paragraph.content) return '';
    return paragraph.content.map(node => {
      if (node.type === 'text') return node.text || '';
      if (node.type === 'fileMention') {
        const path = node.attrs?.path || '';
        const needsQuotes = path.includes(' ');
        return needsQuotes ? `@"${path}"` : `@${path}`;
      }
      return '';
    }).join('');
  }).join('\n');
}

// ── Helper: get plain text before cursor from ProseMirror doc ───────────────

function getTextBeforeCursor(ed: Editor): string {
  const { from } = ed.state.selection;
  let text = '';
  ed.state.doc.nodesBetween(0, from, (node, pos) => {
    if (node.isText && node.text) {
      const start = pos;
      const end = Math.min(pos + node.text.length, from);
      if (end > start) {
        text += node.text.slice(0, end - start);
      }
    } else if (node.type.name === 'paragraph' && pos > 0 && pos < from) {
      text += '\n';
    }
  });
  return text;
}

/**
 * Walk doc text chars to find the ProseMirror position of a given character offset.
 */
function charOffsetToPos(ed: Editor, targetOffset: number): number {
  const { from } = ed.state.selection;
  let charCount = 0;
  let result = -1;
  ed.state.doc.nodesBetween(0, from, (node, pos) => {
    if (result >= 0) return false;
    if (node.isText && node.text) {
      for (let i = 0; i < node.text.length && pos + i < from; i++) {
        if (charCount === targetOffset) {
          result = pos + i;
          return false;
        }
        charCount++;
      }
    } else if (node.type.name === 'paragraph' && pos > 0 && pos < from) {
      if (charCount === targetOffset) {
        result = pos;
        return false;
      }
      charCount++;
    }
  });
  return result;
}

// ── RichTextInput Component ─────────────────────────────────────────────────

export interface RichTextInputProps {
  content: string;
  onChange: (text: string) => void;
  onSubmit: () => void;
  onFileRemove?: (fileName: string) => void;
  onTab?: () => boolean | void;
  onPasteFiles?: (files: File[]) => void;
  fileTree?: FileNode[];
  onAddFile?: (path: string, name: string, type: 'file' | 'folder') => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

export function RichTextInput({
  content,
  onChange,
  onSubmit,
  onFileRemove,
  onTab,
  onPasteFiles,
  fileTree,
  onAddFile,
  placeholder = '',
  disabled = false,
  className = '',
}: RichTextInputProps) {
  const isExternalUpdate = useRef(false);
  const lastSetContent = useRef(content);
  const onChangeRef = useRef(onChange);
  const onSubmitRef = useRef(onSubmit);
  onChangeRef.current = onChange;
  onSubmitRef.current = onSubmit;
  const onTabRef = useRef(onTab);
  onTabRef.current = onTab;
  const onPasteFilesRef = useRef(onPasteFiles);
  onPasteFilesRef.current = onPasteFiles;
  const onAddFileRef = useRef(onAddFile);
  onAddFileRef.current = onAddFile;
  const onFileRemoveRef = useRef(onFileRemove);
  onFileRemoveRef.current = onFileRemove;
  const prevMentionNames = useRef<Set<string>>(new Set());

  // ── @ mention state ─────────────────────────────────────────────────────
  const [mentionActive, setMentionActive] = useState(false);
  const [mentionQuery, setMentionQuery] = useState('');
  const [mentionIndex, setMentionIndex] = useState(0);
  const [dropdownPos, setDropdownPos] = useState<{ top: number; left: number } | null>(null);
  const mentionDropdownRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<Editor | null>(null);

  const mentionActiveRef = useRef(mentionActive);
  mentionActiveRef.current = mentionActive;
  const mentionIndexRef = useRef(mentionIndex);
  mentionIndexRef.current = mentionIndex;

  const hasMentionSupport = !!(fileTree && fileTree.length > 0 && onAddFile);

  const rootPrefix = useMemo(() => {
    if (!fileTree || fileTree.length === 0) return '';
    const first = fileTree[0];
    return (first.path || first.id || '').replace(/[/\\]$/, '');
  }, [fileTree]);

  const allFlatFiles = useMemo(() => {
    if (!fileTree) return [];
    return flattenAllFiles(fileTree, rootPrefix);
  }, [fileTree, rootPrefix]);

  const allFiles = useMemo(() => allFlatFiles.filter(f => f.type === 'file'), [allFlatFiles]);

  const filteredFiles = useMemo((): FlatFileItem[] => {
    if (!mentionActive) return [];
    if (!mentionQuery) return allFiles.slice(0, 100);
    const q = mentionQuery.toLowerCase();
    return allFiles
      .filter(f => f.name.toLowerCase().includes(q) || f.relativePath.toLowerCase().includes(q))
      .slice(0, 100);
  }, [mentionActive, mentionQuery, allFiles]);

  const filteredFilesRef = useRef(filteredFiles);
  filteredFilesRef.current = filteredFiles;

  // ── @ detection ─────────────────────────────────────────────────────────
  const handleMentionDetection = useCallback((ed: Editor) => {
    if (!hasMentionSupport) {
      if (mentionActiveRef.current) setMentionActive(false);
      return;
    }

    const textBefore = getTextBeforeCursor(ed);
    const lastAtIndex = textBefore.lastIndexOf('@');

    if (lastAtIndex >= 0) {
      const charBefore = lastAtIndex > 0 ? textBefore[lastAtIndex - 1] : ' ';
      const isValid = lastAtIndex === 0 || charBefore === '\n' || charBefore === ' ';
      const queryText = textBefore.slice(lastAtIndex + 1);
      const hasNewline = queryText.includes('\n');

      if (isValid && !hasNewline) {
        // Compute pixel position of the @ character for dropdown placement
        const atDocPos = charOffsetToPos(ed, lastAtIndex);
        if (atDocPos >= 0) {
          try {
            const coords = ed.view.coordsAtPos(atDocPos);
            setDropdownPos({ top: coords.bottom + 4, left: coords.left });
          } catch {
            // fallback: no position update
          }
        }
        setMentionActive(true);
        setMentionQuery(queryText);
        setMentionIndex(0);
        return;
      }
    }

    setMentionActive(false);
  }, [hasMentionSupport]);

  // ── File selection handler ──────────────────────────────────────────────
  const handleSelectFile = useCallback((file: FlatFileItem) => {
    const ed = editorRef.current;
    if (!ed || ed.isDestroyed) return;

    onAddFileRef.current?.(file.path, file.name, file.type);

    const textBefore = getTextBeforeCursor(ed);
    const lastAtIndex = textBefore.lastIndexOf('@');
    if (lastAtIndex < 0) return;

    const atPos = charOffsetToPos(ed, lastAtIndex);
    if (atPos >= 0) {
      const { from } = ed.state.selection;
      ed.chain()
        .focus()
        .deleteRange({ from: atPos, to: from })
        .insertContentAt(atPos, {
          type: 'fileMention',
          attrs: { path: file.path, name: file.name },
        })
        .run();
    }

    setMentionActive(false);
    setMentionQuery('');
    setMentionIndex(0);
  }, []);

  const handleSelectFileRef = useRef(handleSelectFile);
  handleSelectFileRef.current = handleSelectFile;

  // ── Editor setup ────────────────────────────────────────────────────────
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: false,
        blockquote: false,
        codeBlock: false,
        code: false,
        bulletList: false,
        orderedList: false,
        listItem: false,
        horizontalRule: false,
        bold: false,
        italic: false,
        strike: false,
        dropcursor: false,
      }),
      FileMention,
    ],
    content: textToTiptapContent(content),
    editable: !disabled,
    onUpdate: ({ editor: ed }) => {
      if (isExternalUpdate.current) return;
      const json = ed.getJSON();
      const text = tiptapContentToText(json);
      lastSetContent.current = text;
      onChangeRef.current(text);

      const currentNames = extractMentionNames(json);
      Array.from(prevMentionNames.current).forEach(name => {
        if (!currentNames.has(name)) {
          onFileRemoveRef.current?.(name);
        }
      });
      prevMentionNames.current = currentNames;

      handleMentionDetection(ed);
    },
    onSelectionUpdate: ({ editor: ed }) => {
      handleMentionDetection(ed);
    },
    editorProps: {
      attributes: {
        class: 'outline-none min-h-[60px] max-h-[200px] overflow-y-auto scrollbar-hide',
      },
      handleDrop: () => true,
      handleDOMEvents: {
        dragover: (_, e) => { e.preventDefault(); return true; },
        dragenter: (_, e) => { e.preventDefault(); return true; },
        drop: (_, e) => {
          const files = Array.from(e.dataTransfer?.files ?? []);
          if (files.length > 0 && onPasteFilesRef.current) {
            e.preventDefault();
            e.stopPropagation();
            onPasteFilesRef.current(files);
            return true;
          }
          return false;
        },
        paste: (_, e) => {
          if (!e.clipboardData?.items || !onPasteFilesRef.current) return false;
          const files = Array.from(e.clipboardData.items)
            .filter(item => item.kind === 'file')
            .flatMap(item => item.getAsFile() ?? []);
          if (files.length > 0) {
            e.preventDefault();
            onPasteFilesRef.current(files);
            return true;
          }
          return false;
        },
      },
      handleKeyDown: (_view, event) => {
        if (mentionActiveRef.current && filteredFilesRef.current.length > 0) {
          if (event.key === 'ArrowDown') {
            event.preventDefault();
            setMentionIndex(i => Math.min(i + 1, filteredFilesRef.current.length - 1));
            return true;
          }
          if (event.key === 'ArrowUp') {
            event.preventDefault();
            setMentionIndex(i => Math.max(i - 1, 0));
            return true;
          }
          if (event.key === 'Enter' || event.key === 'Tab') {
            event.preventDefault();
            const selectedFile = filteredFilesRef.current[mentionIndexRef.current];
            if (selectedFile) handleSelectFileRef.current(selectedFile);
            return true;
          }
          if (event.key === 'Escape') {
            event.preventDefault();
            setMentionActive(false);
            return true;
          }
        }

        if (event.key === 'Tab' && !event.shiftKey) {
          if (onTabRef.current?.()) {
            event.preventDefault();
            return true;
          }
        }

        if (event.key === 'Enter' && !event.shiftKey) {
          event.preventDefault();
          onSubmitRef.current();
          return true;
        }
        return false;
      },
    },
  });

  // Keep editor ref in sync
  useEffect(() => {
    editorRef.current = editor;
  }, [editor]);

  // Sync external content changes into the editor
  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    if (content === lastSetContent.current) return;

    lastSetContent.current = content;
    const json = textToTiptapContent(content);
    queueMicrotask(() => {
      if (!editor || editor.isDestroyed) return;
      isExternalUpdate.current = true;
      editor.commands.setContent(json);
      prevMentionNames.current = extractMentionNames(json);
      isExternalUpdate.current = false;
    });
  }, [content, editor]);

  // Sync disabled state
  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    editor.setEditable(!disabled);
  }, [disabled, editor]);

  // Dismiss dropdown on outside click
  useEffect(() => {
    if (!mentionActive) return;
    const handleMouseDown = (e: MouseEvent) => {
      if (mentionDropdownRef.current && !mentionDropdownRef.current.contains(e.target as HTMLElement)) {
        setMentionActive(false);
      }
    };
    document.addEventListener('mousedown', handleMouseDown);
    return () => document.removeEventListener('mousedown', handleMouseDown);
  }, [mentionActive]);

  // Adjust dropdown if it overflows viewport
  useEffect(() => {
    if (!mentionActive || !dropdownPos || !mentionDropdownRef.current) return;
    const el = mentionDropdownRef.current;
    const rect = el.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let { top, left } = dropdownPos;

    if (rect.right > vw - 8) left = Math.max(8, vw - rect.width - 8);
    if (rect.bottom > vh - 8) top = dropdownPos.top - rect.height - 28;
    if (left !== dropdownPos.left || top !== dropdownPos.top) {
      el.style.top = `${top}px`;
      el.style.left = `${left}px`;
    }
  }, [mentionActive, dropdownPos, filteredFiles]);

  // Scroll active item into view
  useEffect(() => {
    if (!mentionActive) return;
    const active = mentionDropdownRef.current?.querySelector('[data-mention-active="true"]');
    if (active) active.scrollIntoView({ block: 'nearest' });
  }, [mentionIndex, mentionActive]);

  const handleFileRemove = useRef((name: string) => onFileRemoveRef.current?.(name)).current;
  const handleFileReplace = useCallback((oldName: string, newFile: FlatFileItem) => {
    onFileRemoveRef.current?.(oldName);
    onAddFileRef.current?.(newFile.path, newFile.name, newFile.type);
  }, []);

  const mentionCtx = useMemo<FileMentionContextValue>(() => ({
    onRemove: handleFileRemove,
    onReplace: handleFileReplace,
    allFiles: allFiles,
  }), [handleFileRemove, handleFileReplace, allFiles]);

  return (
    <div className={`rich-text-input relative ${className}`}>
      <FileMentionContext.Provider value={mentionCtx}>
        <EditorContent editor={editor} />
      </FileMentionContext.Provider>

      {/* @ Mention dropdown — fixed position near the @ character */}
      {mentionActive && filteredFiles.length > 0 && dropdownPos && (
        <div
          ref={mentionDropdownRef}
          className="fixed max-h-[340px] w-[320px] overflow-y-auto bg-white border border-gray-200 rounded-lg shadow-lg z-[9999]"
          style={{ top: dropdownPos.top, left: dropdownPos.left }}
        >
          <div className="py-1">
            <div className="px-3 py-1.5 text-[10px] text-black/40 font-medium uppercase tracking-wider flex items-center justify-between">
              <span>Files</span>
              <span className="normal-case tracking-normal">
                {filteredFiles.length}{filteredFiles.length >= 100 ? '+' : ''} {mentionQuery ? 'found' : 'total'}
              </span>
            </div>
            {filteredFiles.map((file, idx) => (
              <button
                key={file.path}
                type="button"
                data-mention-active={idx === mentionIndex}
                onClick={() => handleSelectFile(file)}
                onMouseEnter={() => setMentionIndex(idx)}
                className={`w-full flex items-center gap-1.5 px-3 py-1.5 text-left text-xs transition-colors ${
                  idx === mentionIndex
                    ? 'bg-orange-50 text-orange-900'
                    : 'text-gray-700 hover:bg-gray-50'
                }`}
              >
                <FileIcon className="w-3.5 h-3.5 flex-shrink-0 text-gray-400" />
                <span className="font-medium truncate">{file.name}</span>
                <span className="text-[10px] text-black/30 truncate ml-auto flex-shrink-0 max-w-[50%]">
                  {file.relativePath}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      <style>{`
        .rich-text-input .tiptap {
          font-size: 14px;
          line-height: 1.625;
          font-weight: 500;
          color: #1A1A1A;
        }
        .rich-text-input .tiptap p {
          margin: 0;
        }
        .rich-text-input .tiptap .is-editor-empty:first-child::before {
          content: '${placeholder.replace(/'/g, "\\'")}';
          color: rgba(0, 0, 0, 0.2);
          font-weight: 500;
          pointer-events: none;
          float: left;
          height: 0;
        }
      `}</style>
    </div>
  );
}
