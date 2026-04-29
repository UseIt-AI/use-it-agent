import React, { useState, useRef, useEffect, useCallback } from 'react';
import { observer } from 'mobx-react-lite';
import { useNavigate } from 'react-router-dom';
import { useProject } from '@/contexts/ProjectContext';
import { ChevronDown, Plus, Folder, Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const ProjectSwitcher = observer(function ProjectSwitcher() {
  const { currentProject, recentProjects, openProject, createProject, refreshRecentProjects } = useProject();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      refreshRecentProjects();
    }
  }, [isOpen, refreshRecentProjects]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
        setIsCreating(false);
        setNewName('');
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  useEffect(() => {
    if (isCreating && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isCreating]);

  const handleSwitchProject = useCallback(async (projectId: string) => {
    if (projectId === currentProject?.id) {
      setIsOpen(false);
      return;
    }
    const project = await openProject(projectId);
    if (project) {
      navigate('/workspace', { replace: true });
    }
    setIsOpen(false);
  }, [currentProject, openProject, navigate]);

  const handleCreateProject = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    try {
      const project = await createProject(name);
      if (project) {
        navigate('/workspace', { replace: true });
      }
    } catch (err) {
      console.error('Failed to create project:', err);
    }
    setIsCreating(false);
    setNewName('');
    setIsOpen(false);
  }, [newName, createProject, navigate]);

  const startCreating = useCallback(() => {
    const existingNames = recentProjects.map(p => p.name);
    let maxN = 0;
    existingNames.forEach(name => {
      const match = name.match(/^New Project (\d+)$/);
      if (match) maxN = Math.max(maxN, parseInt(match[1], 10));
    });
    setNewName(`New Project ${maxN + 1}`);
    setIsCreating(true);
  }, [recentProjects]);

  const localProjects = recentProjects.filter(p => p.exists !== false);

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="no-drag flex items-center gap-1 rounded-sm text-black/60 hover:bg-black/5 transition-colors text-xs font-medium px-1 py-1"
        title={t('workspace.header.switchProject')}
      >
        <span>{t('workspace.header.switchProject')}</span>
        <ChevronDown className={`w-3 h-3 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 mt-1 w-64 bg-white border border-black/10 shadow-lg z-[9999] rounded-sm overflow-hidden">
          {/* Create new project */}
          {isCreating ? (
            <form onSubmit={handleCreateProject} className="flex items-center gap-1.5 px-2 py-1.5 border-b border-black/5">
              <input
                ref={inputRef}
                value={newName}
                onChange={e => setNewName(e.target.value)}
                className="flex-1 text-xs bg-transparent outline-none text-black/80 placeholder:text-black/30 px-1 py-0.5 border border-black/10 rounded-sm"
                placeholder="Project name..."
                onKeyDown={e => {
                  if (e.key === 'Escape') {
                    setIsCreating(false);
                    setNewName('');
                  }
                }}
              />
              <button
                type="submit"
                disabled={!newName.trim()}
                className="text-[10px] px-2 py-0.5 bg-black text-white font-medium disabled:opacity-40 rounded-sm"
              >
                OK
              </button>
            </form>
          ) : (
            <button
              onClick={startCreating}
              className="w-full flex items-center gap-2 px-3 py-2 text-xs text-black/60 hover:bg-black/5 transition-colors border-b border-black/5"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>{t('workspace.header.newProject', 'New Project')}</span>
            </button>
          )}

          {/* Project list */}
          <div className="max-h-48 overflow-y-auto">
            {localProjects.length === 0 ? (
              <div className="px-3 py-3 text-[10px] text-black/30 text-center font-mono">
                NO PROJECTS
              </div>
            ) : (
              localProjects.map(project => (
                <button
                  key={project.id}
                  onClick={() => handleSwitchProject(project.id)}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-xs transition-colors text-left ${
                    project.id === currentProject?.id
                      ? 'bg-black/5 text-black/90 font-medium'
                      : 'text-black/70 hover:bg-black/5'
                  }`}
                >
                  <Folder className="w-3.5 h-3.5 flex-shrink-0 text-black/40" />
                  <span className="truncate flex-1">{project.name}</span>
                  {project.id === currentProject?.id && (
                    <Check className="w-3.5 h-3.5 flex-shrink-0 text-black/40" />
                  )}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
});

export default ProjectSwitcher;
