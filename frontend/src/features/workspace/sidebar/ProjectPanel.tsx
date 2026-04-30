import clsx from "clsx";
import { AlertTriangle, Cloud, Download, FolderOpen, Loader2, Plus, Trash2, X } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import ListItem, { ListItemActionButton, ListItemActions, ListItemText } from "../control-panel/components/ListItem";
import { useProject } from "@/shared";
import { SyncProjectDialog } from "./SyncProjectDialog";
import { formatRelativeTime } from "@/lib";
import { AlertDialog } from "@/components/AlertDialog";

const generateProjectName = (existingNames: string[]): string => {
  let maxN = 0;
  existingNames.forEach(name => {
    const match = name.match(/^New Project (\d+)$/);
    if (match) maxN = Math.max(maxN, parseInt(match[1], 10));
  });
  return `New Project ${maxN + 1}`;
};

export const ProjectPanel = () => {
  const navigate = useNavigate();
  const { recentProjects, createProject, openProject, deleteProject, isLoading, currentProject, refreshRecentProjects } = useProject();
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [createError, setCreateError] = useState('');
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [syncTarget, setSyncTarget] = useState<{ id: string; name: string } | null>(null);
  const [pendingDeleteProject, setPendingDeleteProject] = useState<{ id: string; name: string } | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const allProjects = useMemo(() =>
    [...recentProjects].sort((a, b) =>
      (b.created_at ?? b.lastModified) - (a.created_at ?? a.lastModified)
    ),
  [recentProjects]);

  const handleCreate = () => {
    setNewName(generateProjectName(recentProjects.map(p => p.name)));
    setCreateError('');
    setCreating(true);
    setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    }, 0);
  };

  const handleCreateSubmit = async () => {
    const name = newName.trim();
    if (!name) {
      setCreating(false);
      return;
    }
    setIsCreatingProject(true);
    try {
      const project = await createProject(name);
      setCreating(false);
      setNewName('');
      setCreateError('');
      if (project) navigate('/workspace');
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : '创建失败');
    } finally {
      setIsCreatingProject(false);
    }
  };

  const handleCreateKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleCreateSubmit();
    if (e.key === 'Escape') {
      setCreating(false);
      setNewName('');
      setCreateError('');
    }
  };

  const handleDelete = (projectId: string, projectName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setPendingDeleteProject({ id: projectId, name: projectName });
  };

  const confirmDeleteProject = async () => {
    if (!pendingDeleteProject) return;
    const { id: projectId } = pendingDeleteProject;
    const isDeletingCurrent = currentProject?.id === projectId;

    setConfirmingDelete(true);
    setDeletingId(projectId);
    try {
      const success = await deleteProject(projectId);
      if (!success) return;

      if (isDeletingCurrent) {
        const freshProjects = await refreshRecentProjects();
        const next = freshProjects.find(p => p.exists !== false && !p.isCloudOnly);
        if (next) {
          await openProject(next.id);
          navigate('/workspace');
        }
      }
    } finally {
      setConfirmingDelete(false);
      setDeletingId(null);
      setPendingDeleteProject(null);
    }
  };

  const handleSelectProject = async (projectId: string) => {
    if (projectId === currentProject?.id) {
      navigate('/workspace');
      return;
    }

    const project = await openProject(projectId);
    if (project) {
      navigate('/workspace');
    }
  };

  return (
    <div className="flex flex-col h-full relative">
      {/* Header */}
      <div className="flex items-center justify-between px-4 h-[36px] border-b border-divider bg-canvas flex-shrink-0">
        <div className="flex items-center gap-2">
          <h3 className="text-[10px] font-bold text-black/40 uppercase tracking-wider">
            My Projects
          </h3>
          <span className="text-[9px] font-mono text-black/40 bg-black/5 px-1 rounded-sm">
            {recentProjects.length}
          </span>
        </div>
        <button
          onClick={handleCreate}
          disabled={creating || isLoading}
          className="p-1 hover:bg-black/5 rounded text-black/40 hover:text-black/80 transition-colors disabled:opacity-50"
          title="New Project"
        >
          {isLoading ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Plus className="w-3.5 h-3.5" />
          )}
        </button>
      </div>

      {/* Inline create input */}
      {creating && (
        <div className="px-2 py-1.5 border-b border-divider bg-white">
          <div className="flex items-center gap-1">
            <input
              ref={inputRef}
              value={newName}
              onChange={(e) => { setNewName(e.target.value); setCreateError(''); }}
              onBlur={(e) => {
                if (e.relatedTarget?.getAttribute('data-cancel')) return;
                handleCreateSubmit();
              }}
              onKeyDown={handleCreateKeyDown}
              disabled={isCreatingProject}
              className="flex-1 min-w-0 bg-white border border-blue-500 rounded px-1.5 py-0.5 text-[11px] text-black/90 focus:outline-none focus:ring-1 focus:ring-blue-500/20 disabled:opacity-50"
            />
            <button
              data-cancel="true"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => { setCreating(false); setNewName(''); setCreateError(''); }}
              className="flex-shrink-0 p-0.5 text-black/30 hover:text-black/70 transition-colors"
              title="取消"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          {createError && (
            <div className="text-[10px] text-red-500 mt-1 px-0.5">{createError}</div>
          )}
        </div>
      )}

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {allProjects.map((project) => {
          const isSelected = project.id === currentProject?.id;
          const isDeleting = project.id === deletingId;
          const isCloudOnly = project.isCloudOnly === true;
          const isMissing = project.exists === false && !isCloudOnly;
          const isClickable = !isDeleting && !isCloudOnly && !isMissing;

          return (
            <ListItem
              key={project.id}
              selected={isSelected}
              disabled={isDeleting}
              onClick={() => {
                if(isClickable)
                  void handleSelectProject(project.id)
              }}
              className={clsx('px-4', !isClickable && !isDeleting && '!cursor-not-allowed hover:bg-transparent')}
            >
              <ListItemText
                primary={project.name}
                secondary={formatRelativeTime(project.lastModified)}
                selected={isSelected}
              />

              {isCloudOnly && (
                <span title="仅在云端"><Cloud className="w-3 h-3 flex-shrink-0 text-blue-400" /></span>
              )}
              {isMissing && (
                <span title="本地文件缺失"><AlertTriangle className="w-3 h-3 flex-shrink-0 text-amber-400" /></span>
              )}

              {isCloudOnly && (
                <ListItemActions showOnHover={false}>
                  <ListItemActionButton
                    onClick={(e) => { e.stopPropagation(); setSyncTarget({ id: project.id, name: project.name }); }}
                    title="从云端同步到本地"
                  >
                    <Download className="w-3.5 h-3.5" />
                  </ListItemActionButton>
                </ListItemActions>
              )}
              <ListItemActions>
                <ListItemActionButton
                  variant="danger"
                  onClick={(e) => handleDelete(project.id, project.name, e)}
                  title="Delete"
                >
                  {isDeleting ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="w-3.5 h-3.5" />
                  )}
                </ListItemActionButton>
              </ListItemActions>
            </ListItem>
          );
        })}

        {!isLoading && recentProjects.length === 0 && !creating && (
          <div className="flex flex-col items-center justify-center py-8 text-black/30">
            <FolderOpen className="w-8 h-8 mb-2 opacity-50" />
            <div className="text-[11px]">No projects yet</div>
          </div>
        )}
      </div>

      {/* Sync dialog */}
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
    </div>
  );
};
