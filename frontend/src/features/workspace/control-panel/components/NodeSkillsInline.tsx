import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, Plus, X } from 'lucide-react';
import type { WorkflowNode } from '@/features/workflow';
import { useSkillsRootPath } from '@/features/workspace/useSkillsRootPath';
import { useSkillsList, type SkillInfo } from '@/features/workspace/useSkillsList';
import { emitSkillsNavigation } from '@/features/workspace/skillsNavigationEvent';

function SkillsAddMenu({
  currentSkillS3Keys,
  options,
  onSelect,
}: {
  /** 当前已选中的 skill S3 keys */
  currentSkillS3Keys: string[];
  /** 可选的 skill 列表 */
  options: SkillInfo[];
  /** 选择 skill 时的回调，传入 S3 key */
  onSelect: (s3Key: string) => void;
}) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const close = () => setOpen(false);

  useEffect(() => {
    if (!open) return;

    const handleClickOutside = (e: MouseEvent) => {
      const t = e.target as Node;
      if (
        menuRef.current &&
        !menuRef.current.contains(t) &&
        triggerRef.current &&
        !triggerRef.current.contains(t)
      ) {
        close();
      }
    };

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setPos({ x: r.right, y: r.bottom + 6 });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const el = menuRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    if (rect.right > vw) el.style.left = `${vw - rect.width - 10}px`;
    if (rect.bottom > vh) el.style.top = `${vh - rect.height - 10}px`;
  }, [open, pos.x, pos.y]);

  return (
    <>
      <button
        ref={triggerRef}
        className="inline-flex items-center justify-center w-5 h-5 text-black/40 hover:text-black/70 hover:bg-black/5 rounded-sm transition-colors flex-shrink-0"
        title="Add skill"
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={options.length === 0}
      >
        <Plus className="w-3.5 h-3.5" />
      </button>

      {open
        ? createPortal(
            <div
              ref={menuRef}
              className="fixed z-50 bg-canvas border border-divider rounded-md shadow-lg py-1 min-w-[200px]"
              style={{
                left: `${pos.x}px`,
                top: `${pos.y}px`,
                transform: 'translateX(-100%)',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              {options.length === 0 ? (
                <div className="px-3 py-1.5 text-xs text-black/40">No skills</div>
              ) : (
                options.map((skill) => {
                  const added = currentSkillS3Keys.includes(skill.s3Key);
                  return (
                    <button
                      key={skill.s3Key}
                      type="button"
                      className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-xs text-black/80 hover:bg-black/5 hover:text-black/90 transition-colors"
                      onClick={() => {
                        onSelect(skill.s3Key);
                        close();
                      }}
                    >
                      <span className="flex-1 truncate">{skill.name}</span>
                      <span className="w-4 h-4 flex items-center justify-center flex-shrink-0">
                        {added ? <Check className="w-3.5 h-3.5 text-black/60" /> : null}
                      </span>
                    </button>
                  );
                })
              )}
            </div>,
            document.body
          )
        : null}
    </>
  );
}

function SkillChip({
  label,
  s3Key,
  onRemove,
  onClick,
}: {
  label: string;
  s3Key: string;
  onRemove: () => void;
  onClick: () => void;
}) {
  return (
    <div className="inline-flex items-center gap-1 bg-black/5 border border-black/10 rounded-full px-1.5 h-[22px] text-[11px] text-black/70 flex-shrink-0">
      <button
        type="button"
        className="truncate max-w-[100px] hover:text-black/90 hover:underline transition-colors cursor-pointer"
        title={`点击查看 ${label}`}
        onClick={onClick}
      >
        {label}
      </button>
      <button
        type="button"
        className="w-3.5 h-3.5 inline-flex items-center justify-center text-black/40 hover:text-black/80 transition-colors"
        onClick={(e) => {
          e.stopPropagation();
          onRemove();
        }}
        title="Remove skill"
      >
        <X className="w-2.5 h-2.5" />
      </button>
    </div>
  );
}

/**
 * 从 S3 key 中提取 skill 名称
 * S3 key 格式: skills/{user_id}/{skill_name}
 */
function extractSkillNameFromS3Key(s3Key: string): string {
  const parts = s3Key.split('/');
  // 返回最后一部分作为 skill 名称
  return parts[parts.length - 1] || s3Key;
}

export function NodeSkillsInline({
  node,
  onUpdate,
}: {
  node: WorkflowNode;
  onUpdate?: (nodeId: string, patch: Record<string, any>) => void;
}) {
  const { rootPath } = useSkillsRootPath();
  const { skills: availableSkills, getSkillNameByS3Key } = useSkillsList(rootPath);

  // 从 node.data 获取 skills（现在存储的是 S3 keys）
  const nodeSkillS3Keys: string[] = Array.isArray((node.data as any)?.skills) ? (node.data as any).skills : [];

  // 使用本地 state 保证即时 UI 反馈
  const [localSkillS3Keys, setLocalSkillS3Keys] = useState<string[]>(nodeSkillS3Keys);

  // 用 JSON.stringify 做稳定的依赖比较，当 node 切换或外部数据变化时同步
  const nodeSkillsKey = JSON.stringify(nodeSkillS3Keys);
  const prevNodeIdRef = useRef(node.id);
  const prevSkillsKeyRef = useRef(nodeSkillsKey);

  if (node.id !== prevNodeIdRef.current || nodeSkillsKey !== prevSkillsKeyRef.current) {
    // 同步渲染期更新（避免 useEffect 延迟导致闪烁）
    prevNodeIdRef.current = node.id;
    prevSkillsKeyRef.current = nodeSkillsKey;
    setLocalSkillS3Keys(nodeSkillS3Keys);
  }

  const handleAddSkill = (s3Key: string) => {
    if (localSkillS3Keys.includes(s3Key)) return;
    const next = [...localSkillS3Keys, s3Key];
    setLocalSkillS3Keys(next);
    onUpdate?.(node.id, { skills: next });
  };

  const handleRemoveSkill = (s3Key: string) => {
    const next = localSkillS3Keys.filter((k: string) => k !== s3Key);
    setLocalSkillS3Keys(next);
    onUpdate?.(node.id, { skills: next });
  };

  /** 获取 skill 的显示名称 */
  const getDisplayName = (s3Key: string): string => {
    // 优先从 availableSkills 中查找
    const name = getSkillNameByS3Key(s3Key);
    if (name) return name;
    // 如果找不到（可能是其他用户的 skill 或已删除），从 S3 key 中提取
    return extractSkillNameFromS3Key(s3Key);
  };

  /** 点击 skill chip 时导航到 Skills 页面并展开对应文件夹 */
  const handleSkillClick = (s3Key: string) => {
    const skillName = getDisplayName(s3Key);
    emitSkillsNavigation({ skillName, s3Key });
  };

  return (
    <div className="flex items-center gap-1 overflow-hidden flex-nowrap">
      <span className="text-[11px] text-black/40 flex-shrink-0">Skills</span>
      {localSkillS3Keys.map((s3Key: string) => (
        <SkillChip
          key={s3Key}
          label={getDisplayName(s3Key)}
          s3Key={s3Key}
          onRemove={() => handleRemoveSkill(s3Key)}
          onClick={() => handleSkillClick(s3Key)}
        />
      ))}
      <SkillsAddMenu currentSkillS3Keys={localSkillS3Keys} options={availableSkills} onSelect={handleAddSkill} />
    </div>
  );
}
