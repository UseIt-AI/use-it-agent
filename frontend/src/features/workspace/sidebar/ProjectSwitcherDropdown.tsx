import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { observer } from 'mobx-react-lite'
import { AlertTriangle, Check, ChevronDown, Cloud, Download, FolderOpen, Loader2, Plus, Trash2 } from 'lucide-react';
import clsx from 'clsx';
import { useProject } from '@/shared';
import { SyncProjectDialog } from './SyncProjectDialog';
import { formatRelativeTime } from '@/lib';
import { AlertDialog } from '@/components/AlertDialog';

const generateProjectName = (existingNames: string[]): string => {
  let maxN = 0;
  existingNames.forEach(name => {
    const match = name.match(/^New Project (\d+)$/);
    if (match) maxN = Math.max(maxN, parseInt(match[1], 10));
  });
  return `New Project ${maxN + 1}`;
};

export const ProjectSwitcherDropdown = observer(function ProjectSwitcherDropdown() {
  const navigate = useNavigate();
  const { recentProjects, createProject, openProject, deleteProject, isLoading, isSwitching, currentProject, refreshRecentProjects } = useProject();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [newName, setNewName] = useState('');
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [syncTarget, setSyncTarget] = useState<{ id: string; name: string } | null>(null);
  const [pendingDeleteProject, setPendingDeleteProject] = useState<{ id: string; name: string } | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const allProjects = useMemo(() =>
    [...recentProjects].sort((a, b) =>
      (b.created_at ?? b.lastModified) - (a.created_at ?? a.lastModified)
    ),
    [recentProjects],
  );

  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (
        triggerRef.current?.contains(e.target as Node) ||
        dropdownRef.current?.contains(e.target as Node)
      ) return;
      setOpen(false);
      setCreating(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  const handleToggle = useCallback(() => {
    if (!open && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      setPos({ top: rect.bottom + 4, left: rect.left + rect.width / 2 });
    }
    setOpen(o => !o);
  }, [open]);

  const handleSelect = useCallback(async (projectId: string) => {
    if (isLoading) return;
    if (projectId === currentProject?.id) { 
      setOpen(false); 
      return; 
    }
    setOpen(false);
    await openProject(projectId);
  }, [isSwitching, currentProject, openProject, navigate]);

  const handleDelete = useCallback((projectId: string, projectName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setPendingDeleteProject({ id: projectId, name: projectName });
    setOpen(false)
  }, []);

  const confirmDeleteProject = useCallback(async () => {
    if (!pendingDeleteProject) return;
    const { id: projectId } = pendingDeleteProject;
    const isDeletingCurrent = currentProject?.id === projectId;

    setConfirmingDelete(true);
    setDeletingId(projectId);
    try {
      await deleteProject(projectId);

      if (isDeletingCurrent) {
        const freshProjects = await refreshRecentProjects();
        const next = freshProjects.find(p => p.exists !== false && !p.isCloudOnly);
        if (next) {
          await openProject(next.id);
          navigate('/workspace', { replace: true });
        }
      }
    } finally {
      setConfirmingDelete(false);
      setDeletingId(null);
      setPendingDeleteProject(null);
    }
  }, [pendingDeleteProject, currentProject, openProject, deleteProject, refreshRecentProjects, navigate]);

  const handleStartCreate = () => {
    setNewName(generateProjectName(recentProjects.map(p => p.name)));
    setCreating(true);
    setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    }, 0);
  };

  const handleCreateSubmit = async () => {
    if (submitting) return;
    const name = newName.trim();
    if (!name) { setCreating(false); return; }
    setSubmitting(true);
    try {
      const project = await createProject(name);
      setCreating(false);
      setNewName('');
      if (project) {
        await openProject(project.id);
        setOpen(false);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <button
        ref={triggerRef}
        onClick={handleToggle}
        className="p-1 text-black/30 hover:text-black/60 hover:bg-black/5 rounded transition-colors"
        title="Switch Project"
      >
        <ChevronDown className={clsx("w-3 h-3 transition-transform", open && "rotate-180")} />
      </button>

      {open && createPortal(
        <div
          ref={dropdownRef}
          className="fixed w-[240px] bg-white border border-black/10 rounded-lg shadow-lg py-1 animate-in fade-in zoom-in-95 duration-150"
          style={{ top: pos.top, left: pos.left, transform: 'translateX(-50%)', zIndex: 99999 }}
        >
          <div className="px-2.5 py-1.5 text-[9px] font-bold text-black/30 uppercase tracking-wider">
            Projects
          </div>

          <div className="max-h-[280px] overflow-y-auto">
            {allProjects.map((project) => {
              const isCurrent = project.id === currentProject?.id;
              const isDeleting = project.id === deletingId;
              const isCloudOnly = project.isCloudOnly === true;
              const isMissing = project.exists === false && !isCloudOnly;
              const isClickable = !isDeleting && !isCloudOnly && !isMissing && !isSwitching;

              return (
                <div
                  key={project.id}
                  onClick={() => isClickable && handleSelect(project.id)}
                  className={clsx(
                    'group flex items-center gap-2 px-2.5 py-1.5 text-[11px] transition-colors',
                    isDeleting && 'opacity-50',
                    !isClickable && !isDeleting ? 'cursor-not-allowed' : 'cursor-pointer',
                    isCurrent
                      ? 'bg-black/[0.04] text-black/80'
                      : isClickable ? 'text-black/60 hover:bg-black/[0.03] hover:text-black/80' : 'text-black/40',
                  )}
                >
                  <FolderOpen className="w-3 h-3 flex-shrink-0 text-black/30" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className={clsx("truncate", isCurrent && "font-medium")}>{project.name}</span>
                      {isCloudOnly && <Cloud className="w-2.5 h-2.5 flex-shrink-0 text-blue-400" title="仅在云端" />}
                      {isMissing && <AlertTriangle className="w-2.5 h-2.5 flex-shrink-0 text-amber-400" title="本地文件缺失" />}
                    </div>
                    <div className="text-[9px] text-black/30">{formatRelativeTime(project.lastModified)}</div>
                  </div>

                  <div className="flex items-center gap-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                    {isCloudOnly && (
                      <button
                        onClick={(e) => { e.stopPropagation(); setSyncTarget({ id: project.id, name: project.name }); }}
                        className="p-0.5 text-blue-400 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors"
                        title="从云端同步到本地"
                      >
                        <Download className="w-3 h-3" />
                      </button>
                    )}
                    <button
                      onClick={(e) => handleDelete(project.id, project.name, e)}
                      className="p-0.5 text-black/20 hover:text-red-500 hover:bg-red-50 rounded transition-colors"
                      title="Delete"
                    >
                      {isDeleting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                    </button>
                  </div>

                  {isCurrent && <Check className="w-3 h-3 flex-shrink-0 text-black/40" />}
                </div>
              );
            })}

            {isLoading && allProjects.length === 0 && (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-black/30" />
              </div>
            )}

            {!isLoading && allProjects.length === 0 && (
              <div className="flex flex-col items-center py-4 text-black/30">
                <FolderOpen className="w-5 h-5 mb-1 opacity-50" />
                <span className="text-[10px]">No projects yet</span>
              </div>
            )}
          </div>

          <div className="border-t border-black/[0.06] mt-1 pt-1">
            {creating ? (
              <div className="px-2 py-1 flex items-center gap-1.5">
                <input
                  ref={inputRef}
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') { e.preventDefault(); handleCreateSubmit(); }
                    if (e.key === 'Escape') { setCreating(false); setNewName(''); }
                  }}
                  onBlur={handleCreateSubmit}
                  disabled={submitting}
                  className={clsx(
                    "flex-1 bg-white border rounded px-1.5 py-0.5 text-[11px] text-black/90 focus:outline-none focus:ring-1",
                    submitting
                      ? "border-black/10 text-black/40 cursor-wait"
                      : "border-blue-500 focus:ring-blue-500/20",
                  )}
                  placeholder="Project name..."
                />
                {submitting && <Loader2 className="w-3 h-3 animate-spin text-black/30 flex-shrink-0" />}
              </div>
            ) : (
              <button
                onClick={handleStartCreate}
                className="w-full flex items-center gap-2 px-2.5 py-1.5 text-[11px] text-black/50 hover:bg-black/[0.03] hover:text-black/80 transition-colors"
              >
                <Plus className="w-3 h-3" />
                <span>New Project</span>
              </button>
            )}
          </div>
        </div>,
        document.body,
      )}

      {syncTarget && (
        <SyncProjectDialog
          project={syncTarget}
          onClose={() => setSyncTarget(null)}
          onSyncComplete={refreshRecentProjects}
        />
      )}

      <AlertDialog
        open={!!pendingDeleteProject}
        title="Delete Project?"
        description={`Are you sure you want to delete "${pendingDeleteProject?.name}"? This will delete all cloud and local files and cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={confirmDeleteProject}
        onCancel={() => setPendingDeleteProject(null)}
        isDestructive={true}
        loading={confirmingDelete}
      />
    </>
  );
});
