import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { createPortal } from 'react-dom';
import {
  X,
  Loader2,
  Upload,
  Trash2,
  FileText,
  Wrench,
  Send,
  CheckCircle,
  Clock,
  Globe,
  Archive,
  Plus,
  MessageSquare,
} from 'lucide-react';
import type { Workflow, WorkflowPublication, BundledAsset, WorkflowStatus } from '../../../types';
import { workflowApi } from '../../../api';
import { LOCAL_OFFLINE_USER_ID } from '@/services/localOfflineStore';
import { CATEGORIES } from './publishConstants';
import { parseQuickStartMessage } from '../../../utils/quickStartParser';
import { FileTreePicker, getAllFilePaths, type TreeNode } from './FileTreePicker';
import { getFileIcon } from '@/features/workspace/file-explorer/utils/fileIcon';

function buildStoragePath(workflowId: string, assetType: 'skill' | 'example', relativePath: string): string {
  const safePath = relativePath.replace(/\\/g, '/').replace(/^\//, '');
  const folder = assetType === 'skill' ? 'skills' : 'examples';
  return `workflow_assets/${workflowId}/${folder}/${safePath}`;
}

function guessContentType(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const map: Record<string, string> = {
    py: 'text/x-python', js: 'application/javascript', ts: 'application/typescript',
    json: 'application/json', txt: 'text/plain', md: 'text/markdown',
    csv: 'text/csv', xml: 'application/xml', yaml: 'text/yaml', yml: 'text/yaml',
    html: 'text/html', css: 'text/css', sql: 'text/plain',
    xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    xls: 'application/vnd.ms-excel',
    docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    doc: 'application/msword',
    pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    ppt: 'application/vnd.ms-powerpoint',
    pdf: 'application/pdf', zip: 'application/zip',
    png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif',
    svg: 'image/svg+xml', webp: 'image/webp',
  };
  return map[ext] || 'application/octet-stream';
}

function findFileSize(trees: TreeNode[], absPath: string): number {
  const normalize = (p: string) => p.replace(/\\/g, '/');
  const target = normalize(absPath);
  function walk(nodes: TreeNode[]): number {
    for (const n of nodes) {
      if (n.type === 'file' && normalize(n.path) === target) return n.size ?? 0;
      if (n.children) { const s = walk(n.children); if (s > 0) return s; }
    }
    return 0;
  }
  return walk(trees);
}

interface PublishDialogProps {
  open: boolean;
  workflow: Workflow;
  onClose: () => void;
  onUpdated: (workflow: Workflow) => void;
}

const STATUS_CONFIG: Record<WorkflowStatus, { label: string; icon: React.ElementType; color: string }> = {
  draft: { label: 'Draft', icon: FileText, color: 'text-gray-500 bg-gray-50' },
  pending: { label: 'Pending Review', icon: Clock, color: 'text-amber-600 bg-amber-50' },
  published: { label: 'Published', icon: Globe, color: 'text-emerald-600 bg-emerald-50' },
  archived: { label: 'Archived', icon: Archive, color: 'text-gray-500 bg-gray-50' },
};

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function extractUsedSkillNames(workflow: Workflow): Set<string> {
  const names = new Set<string>();
  const nodes = workflow.definition?.nodes;
  if (!nodes) return names;
  for (const node of nodes) {
    const skills: string[] = (node.data as any)?.skills ?? [];
    for (const s3Key of skills) {
      const name = s3Key.split('/').pop();
      if (name) names.add(name);
    }
  }
  return names;
}

export function PublishDialog({ open, workflow, onClose, onUpdated }: PublishDialogProps) {
  const [publication, setPublication] = useState<WorkflowPublication | null>(null);
  const [pubLoading, setPubLoading] = useState(false);
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [tags, setTags] = useState('');
  const [bundledSkills, setBundledSkills] = useState<BundledAsset[]>([]);
  const [exampleFiles, setExampleFiles] = useState<BundledAsset[]>([]);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');
  const [error, setError] = useState('');
  const [quickStartMessages, setQuickStartMessages] = useState<string[]>([]);
  const quickStartInputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // @ autocomplete state
  const [autoCompleteIndex, setAutoCompleteIndex] = useState<number | null>(null);
  const [autoCompleteQuery, setAutoCompleteQuery] = useState('');
  const [autoCompleteHighlight, setAutoCompleteHighlight] = useState(0);
  const [editingMsgIndex, setEditingMsgIndex] = useState<number | null>(null);

  // Skills picker state
  const [skillsTree, setSkillsTree] = useState<TreeNode[]>([]);
  const [selectedSkillPaths, setSelectedSkillPaths] = useState<Set<string>>(new Set());
  const [skillsLoading, setSkillsLoading] = useState(false);

  // Example files picker state
  const [projectTree, setProjectTree] = useState<TreeNode[]>([]);
  const [selectedFilePaths, setSelectedFilePaths] = useState<Set<string>>(new Set());
  const [projectLoading, setProjectLoading] = useState(false);
  const [fileTreeExpanded, setFileTreeExpanded] = useState(false);
  const [projectRootPath, setProjectRootPath] = useState('');

  const electron = (window as any).electron;

  useEffect(() => {
    if (workflow && open) {
      setDescription(workflow.description ?? '');
      setQuickStartMessages(workflow.quick_start_messages ?? []);
      setAutoCompleteIndex(null);
      setError('');
      setUploadProgress('');
      setFileTreeExpanded(false);
      setSkillsTree([]);
      setProjectTree([]);
      setSelectedSkillPaths(new Set());
      setSelectedFilePaths(new Set());

      // Load publication data first, then load trees with the fetched data
      setPubLoading(true);
      workflowApi.getPublication(workflow.id).then(pub => {
        setPublication(pub);
        setCategory(pub?.category ?? '');
        setTags((pub?.tags ?? []).join(', '));
        const skills = pub?.bundled_skills ?? [];
        const examples = pub?.example_files ?? [];
        setBundledSkills(skills);
        setExampleFiles(examples);
        loadSkillsTree(skills);
        loadProjectTree(examples);
      }).catch(err => {
        console.error('Failed to load publication:', err);
        setCategory('');
        setTags('');
        setBundledSkills([]);
        setExampleFiles([]);
        loadSkillsTree([]);
        loadProjectTree([]);
      }).finally(() => {
        setPubLoading(false);
      });
    }
  }, [workflow, open]);

  const allBundledFiles = useMemo(() => {
    const normalize = (p: string) => p.replace(/\\/g, '/');
    const existing = [...(exampleFiles ?? [])];
    const existingRelPaths = new Set(existing.map(a => normalize(a.relative_path)));

    const virtualEntries: { s3_key: string; filename: string; relative_path: string; size_bytes: number; content_type: string }[] = [];
    const projectBase = projectRootPath ? normalize(projectRootPath).replace(/\/$/, '') : '';

    for (const absPath of selectedFilePaths) {
      const norm = normalize(absPath);
      const rel = projectBase && norm.startsWith(projectBase + '/')
        ? norm.slice(projectBase.length + 1)
        : norm.split('/').pop() || norm;
      if (!existingRelPaths.has(rel)) {
        virtualEntries.push({ s3_key: '', filename: rel.split('/').pop() || rel, relative_path: rel, size_bytes: 0, content_type: '' });
        existingRelPaths.add(rel);
      }
    }

    return [...existing, ...virtualEntries];
  }, [exampleFiles, selectedFilePaths, projectRootPath]);

  const detectAtQuery = (value: string, cursorPos: number): string | null => {
    const before = value.slice(0, cursorPos);
    const atIdx = before.lastIndexOf('@');
    if (atIdx === -1) return null;
    const textBetween = before.slice(atIdx + 1);
    // @"..." quoted form — still typing inside quotes
    if (textBetween.startsWith('"')) {
      if (textBetween.indexOf('"', 1) !== -1) return null; // closing quote found, done
      return textBetween.slice(1);
    }
    if (textBetween.includes(' ')) return null;
    return textBetween;
  };

  const handleQuickStartChange = (index: number, value: string) => {
    setQuickStartMessages(prev => {
      const next = [...prev];
      next[index] = value;
      return next;
    });

    const input = quickStartInputRefs.current[index];
    const cursorPos = input?.selectionStart ?? value.length;
    const query = detectAtQuery(value, cursorPos);

    if (query !== null) {
      setAutoCompleteIndex(index);
      setAutoCompleteQuery(query);
      setAutoCompleteHighlight(0);
    } else {
      setAutoCompleteIndex(null);
    }
  };

  const insertAutoComplete = (index: number, relativePath: string) => {
    const input = quickStartInputRefs.current[index];
    const value = quickStartMessages[index] || '';
    const cursorPos = input?.selectionStart ?? value.length;
    const before = value.slice(0, cursorPos);
    const after = value.slice(cursorPos);
    const atIdx = before.lastIndexOf('@');
    if (atIdx === -1) return;

    const needsQuotes = relativePath.includes(' ');
    const ref = needsQuotes ? `@"${relativePath}"` : `@${relativePath}`;
    // Strip any partial @, @", or @query the user typed
    const prefix = before.slice(0, atIdx);
    const newValue = prefix + ref + ' ' + after;
    setQuickStartMessages(prev => {
      const next = [...prev];
      next[index] = newValue;
      return next;
    });
    setAutoCompleteIndex(null);

    requestAnimationFrame(() => {
      const newCursorPos = prefix.length + ref.length + 1;
      input?.focus();
      input?.setSelectionRange(newCursorPos, newCursorPos);
    });
  };

  const getFilteredSuggestions = () => {
    if (autoCompleteIndex === null) return [];
    const q = autoCompleteQuery.toLowerCase();
    return allBundledFiles.filter(f =>
      f.relative_path.toLowerCase().includes(q) || f.filename.toLowerCase().includes(q)
    );
  };

  // ========== Skills picker ==========
  const loadSkillsTree = useCallback(async (bundledSkillsData: BundledAsset[] = []) => {
    if (!electron) return;
    setSkillsLoading(true);
    try {
      const rootPath = await electron.fsGetSkillsRoot(LOCAL_OFFLINE_USER_ID);
      const tree = await electron.fsReadDirectoryTree(rootPath);
      const children: TreeNode[] = (tree?.children ?? []).filter((n: TreeNode) => n.type === 'folder');
      setSkillsTree(children);

      // Auto-select skills used by the workflow
      const usedNames = extractUsedSkillNames(workflow);
      const autoSelected = new Set<string>();
      for (const folder of children) {
        if (usedNames.has(folder.name)) {
          for (const p of getAllFilePaths(folder)) {
            autoSelected.add(p);
          }
        }
      }
      // Also re-select previously uploaded skills
      if (bundledSkillsData.length > 0) {
        const normalize = (p: string) => p.replace(/\\/g, '/');
        for (const folder of children) {
          const folderFiles = getAllFilePaths(folder);
          for (const fp of folderFiles) {
            const rel = normalize(fp).split('/').slice(-2).join('/');
            if (bundledSkillsData.some(a => normalize(a.relative_path) === rel)) {
              autoSelected.add(fp);
            }
          }
        }
      }
      setSelectedSkillPaths(autoSelected);
    } catch (err) {
      console.error('Failed to load skills tree:', err);
    } finally {
      setSkillsLoading(false);
    }
  }, [electron, workflow]);

  const handleToggleSkill = useCallback((path: string, node: TreeNode) => {
    setSelectedSkillPaths(prev => {
      const next = new Set(prev);
      const paths = node.type === 'folder' ? getAllFilePaths(node) : [path];
      const allSelected = paths.every(p => next.has(p));
      if (allSelected) {
        paths.forEach(p => next.delete(p));
      } else {
        paths.forEach(p => next.add(p));
      }
      return next;
    });
  }, []);

  const uploadSelectedSkills = useCallback(async (): Promise<BundledAsset[]> => {
    if (!electron || selectedSkillPaths.size === 0) return bundledSkills;

    const rootPath = await electron.fsGetSkillsRoot(LOCAL_OFFLINE_USER_ID);
    const normalize = (p: string) => p.replace(/\\/g, '/');
    const base = normalize(rootPath).replace(/\/$/, '');

    const files = Array.from(selectedSkillPaths).map(absPath => {
      const abs = normalize(absPath);
      const rel = abs.startsWith(base + '/') ? abs.slice(base.length + 1) : absPath.split(/[/\\]/).pop()!;
      return { absolutePath: absPath, name: rel.split('/').pop()!, relativePath: rel, size: findFileSize(skillsTree, absPath) };
    });

    setUploadProgress(`Preparing ${files.length} skill file(s)...`);

    const newAssets: BundledAsset[] = [];
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const storagePath = buildStoragePath(workflow.id, 'skill', file.relativePath);
      const contentType = guessContentType(file.name);
      setUploadProgress(`Recording skill ${i + 1}/${files.length}: ${file.name}`);
      newAssets.push({
        s3_key: storagePath,
        filename: file.name,
        relative_path: file.relativePath,
        size_bytes: file.size || 0,
        content_type: contentType,
      });
    }

    return mergeAssets(bundledSkills, newAssets);
  }, [electron, selectedSkillPaths, workflow.id, bundledSkills]);

  // ========== Example files picker ==========
  const loadProjectTree = useCallback(async (exampleFilesData: BundledAsset[] = []) => {
    if (!electron) return;
    setProjectLoading(true);
    try {
      const projectId = (window as any).__currentProjectId;
      const rootPath = await electron.fsGetProjectRoot(projectId);
      setProjectRootPath(rootPath);
      const tree = await electron.fsReadDirectoryTree(rootPath);
      const children: TreeNode[] = (tree?.children ?? []).filter(
        (n: TreeNode) => !(n.type === 'folder' && (n.name === '.cua' || n.name === 'node_modules' || n.name === '.git'))
      );
      setProjectTree(children);

      if (exampleFilesData.length > 0) {
        const normalize = (p: string) => p.replace(/\\/g, '/');
        const baseNorm = normalize(rootPath).replace(/\/$/, '');
        const autoSelected = new Set<string>();
        const allPaths = children.flatMap(getAllFilePaths);
        for (const fp of allPaths) {
          const rel = normalize(fp).startsWith(baseNorm + '/')
            ? normalize(fp).slice(baseNorm.length + 1)
            : fp;
          if (exampleFilesData.some(a => normalize(a.relative_path) === rel)) {
            autoSelected.add(fp);
          }
        }
        setSelectedFilePaths(autoSelected);
      } else {
        setSelectedFilePaths(new Set());
      }
    } catch (err) {
      console.error('Failed to load project tree:', err);
    } finally {
      setProjectLoading(false);
    }
  }, [electron]);

  const handleToggleFile = useCallback((path: string, node: TreeNode) => {
    setSelectedFilePaths(prev => {
      const next = new Set(prev);
      const paths = node.type === 'folder' ? getAllFilePaths(node) : [path];
      const allSelected = paths.every(p => next.has(p));
      if (allSelected) {
        paths.forEach(p => next.delete(p));
      } else {
        paths.forEach(p => next.add(p));
      }
      return next;
    });
  }, []);

  const uploadSelectedExampleFiles = useCallback(async (): Promise<BundledAsset[]> => {
    if (!electron || selectedFilePaths.size === 0) return exampleFiles;

    const projectId = (window as any).__currentProjectId;
    const rootPath = await electron.fsGetProjectRoot(projectId);
    const normalize = (p: string) => p.replace(/\\/g, '/');
    const base = normalize(rootPath).replace(/\/$/, '');

    const files = Array.from(selectedFilePaths).map(absPath => {
      const abs = normalize(absPath);
      const rel = abs.startsWith(base + '/') ? abs.slice(base.length + 1) : absPath.split(/[/\\]/).pop()!;
      return { absolutePath: absPath, name: rel.split('/').pop()!, relativePath: rel, size: findFileSize(projectTree, absPath) };
    });

    setUploadProgress(`Preparing ${files.length} example file(s)...`);

    const newAssets: BundledAsset[] = [];
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const storagePath = buildStoragePath(workflow.id, 'example', file.relativePath);
      const contentType = guessContentType(file.name);
      setUploadProgress(`Recording example ${i + 1}/${files.length}: ${file.name}`);
      newAssets.push({
        s3_key: storagePath,
        filename: file.name,
        relative_path: file.relativePath,
        size_bytes: file.size || 0,
        content_type: contentType,
      });
    }

    return mergeAssets(exampleFiles, newAssets);
  }, [electron, selectedFilePaths, workflow.id, exampleFiles]);

  // ========== Save / Submit ==========
  const handleSubmitForReview = async () => {
    setSubmitting(true);
    setUploading(true);
    setError('');
    try {
      const finalSkills = await uploadSelectedSkills();
      const finalExamples = await uploadSelectedExampleFiles();
      setBundledSkills(finalSkills);
      setExampleFiles(finalExamples);

      const parsedTags = tags.split(',').map(t => t.trim()).filter(Boolean);
      const cleanedMessages = quickStartMessages.map(m => m.trim()).filter(Boolean);

      // Update workflow fields (description, quick_start_messages)
      const updated = await workflowApi.update(workflow.id, {
        description: description || undefined,
        quick_start_messages: cleanedMessages,
      });

      // Upsert publication fields (category, tags, bundled_skills, example_files, status)
      await workflowApi.upsertPublication(workflow.id, {
        category: category || null,
        tags: parsedTags,
        bundled_skills: finalSkills,
        example_files: finalExamples,
        status: 'pending',
      });

      onUpdated(updated);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to submit for review');
    } finally {
      setSubmitting(false);
      setUploading(false);
    }
  };

  const handleSaveDraft = async () => {
    setSubmitting(true);
    setUploading(true);
    setError('');
    try {
      const finalSkills = await uploadSelectedSkills();
      const finalExamples = await uploadSelectedExampleFiles();
      setBundledSkills(finalSkills);
      setExampleFiles(finalExamples);

      const parsedTags = tags.split(',').map(t => t.trim()).filter(Boolean);
      const cleanedMessages = quickStartMessages.map(m => m.trim()).filter(Boolean);

      // Update workflow fields
      const updated = await workflowApi.update(workflow.id, {
        description: description || undefined,
        quick_start_messages: cleanedMessages,
      });

      // Upsert publication fields
      await workflowApi.upsertPublication(workflow.id, {
        category: category || null,
        tags: parsedTags,
        bundled_skills: finalSkills,
        example_files: finalExamples,
      });

      onUpdated(updated);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to save');
    } finally {
      setSubmitting(false);
      setUploading(false);
    }
  };

  if (!open) return null;

  const pubStatus = publication?.status ?? 'draft';
  const statusCfg = STATUS_CONFIG[pubStatus] ?? STATUS_CONFIG.draft;
  const StatusIcon = statusCfg.icon;
  const isPendingOrPublished = pubStatus === 'pending' || pubStatus === 'published';

  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-white shadow-xl border border-gray-200 w-full max-w-2xl mx-4 max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold text-gray-900">Publish Workflow</h2>
            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium ${statusCfg.color}`}>
              <StatusIcon className="w-3.5 h-3.5" />
              {statusCfg.label}
            </span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          <section className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-1">Description</label>
              <textarea
                value={description}
                onChange={e => setDescription(e.target.value)}
                rows={2}
                className="w-full border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-black/10 focus:border-gray-400 resize-none"
                placeholder="What does this agent do?"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-600 mb-1">Category</label>
                <select
                  value={category}
                  onChange={e => setCategory(e.target.value)}
                  className="w-full border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-black/10 focus:border-gray-400 bg-white"
                >
                  <option value="">None</option>
                  {CATEGORIES.map(c => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-600 mb-1">Tags</label>
                <input
                  value={tags}
                  onChange={e => setTags(e.target.value)}
                  className="w-full border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-black/10 focus:border-gray-400"
                  placeholder="excel, report (comma separated)"
                />
              </div>
            </div>
          </section>

          {/* Bundled Skills */}
          <section className="space-y-3">
            <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <Wrench className="w-4 h-4 text-gray-400" />
              Bundled Skills
              {selectedSkillPaths.size > 0 && (
                <span className="text-[10px] text-gray-400 font-normal">({selectedSkillPaths.size} files selected)</span>
              )}
            </h3>
            {skillsLoading ? (
              <div className="flex items-center justify-center py-4 text-xs text-gray-400">
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
                Loading skills...
              </div>
            ) : skillsTree.length > 0 ? (
              <div className="space-y-1.5">
                <p className="text-[11px] text-gray-400">
                  Skills used by this workflow are pre-selected. You can add or remove skills.
                </p>
                <FileTreePicker
                  nodes={skillsTree}
                  selected={selectedSkillPaths}
                  onToggle={handleToggleSkill}
                  mode="flat"
                />
              </div>
            ) : (
              <p className="text-xs text-gray-400 italic py-2">No skills found in your skills directory.</p>
            )}
          </section>

          {/* Example Files */}
          <section className="space-y-3">
            <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <Upload className="w-4 h-4 text-gray-400" />
              Example Files
              {selectedFilePaths.size > 0 && (
                <span className="text-[10px] text-gray-400 font-normal">({selectedFilePaths.size} files selected)</span>
              )}
            </h3>
            {projectLoading ? (
              <div className="flex items-center justify-center py-4 text-xs text-gray-400">
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
                Loading project files...
              </div>
            ) : projectTree.length > 0 ? (
              <div className="space-y-1.5">
                <p className="text-[11px] text-gray-400">
                  Select files from your project to bundle as examples.
                </p>
                <div
                  className="border border-gray-200 overflow-hidden transition-all duration-200"
                  style={{ maxHeight: fileTreeExpanded ? '400px' : '150px' }}
                >
                  <div className="overflow-y-auto py-1" style={{ maxHeight: fileTreeExpanded ? '400px' : '150px' }}>
                    <FileTreePicker
                      nodes={projectTree}
                      selected={selectedFilePaths}
                      onToggle={handleToggleFile}
                      mode="tree"
                    />
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setFileTreeExpanded(!fileTreeExpanded)}
                  className="flex items-center justify-center gap-1 w-full py-1.5 text-[11px] text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors"
                >
                  {fileTreeExpanded ? 'Show less' : 'Show more'}
                </button>
              </div>
            ) : (
              <p className="text-xs text-gray-400 italic py-2">No project files found.</p>
            )}
          </section>

          {/* Quick Start Messages */}
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-gray-400" />
                Quick Start Messages
              </h3>
            </div>
            <div className="flex flex-col gap-2">
              {quickStartMessages.map((msg, index) => {
                const isEditing = editingMsgIndex === index;
                const suggestions = autoCompleteIndex === index ? getFilteredSuggestions() : [];
                const hasFileRefs = msg.includes('@');
                return (
                <div key={index} className="flex items-center gap-1.5">
                  <div className="relative flex-1">
                    {isEditing ? (
                      <input
                        ref={(el) => { quickStartInputRefs.current[index] = el; }}
                        type="text"
                        value={msg}
                        onChange={(e) => handleQuickStartChange(index, e.target.value)}
                        onBlur={() => {
                          setTimeout(() => {
                            setAutoCompleteIndex(null);
                            setEditingMsgIndex(null);
                          }, 150);
                        }}
                        onKeyDown={(e) => {
                          if (autoCompleteIndex === index && suggestions.length > 0) {
                            if (e.key === 'ArrowDown') {
                              e.preventDefault();
                              setAutoCompleteHighlight(h => Math.min(h + 1, suggestions.length - 1));
                            } else if (e.key === 'ArrowUp') {
                              e.preventDefault();
                              setAutoCompleteHighlight(h => Math.max(h - 1, 0));
                            } else if (e.key === 'Enter' || e.key === 'Tab') {
                              e.preventDefault();
                              insertAutoComplete(index, suggestions[autoCompleteHighlight].relative_path);
                            } else if (e.key === 'Escape') {
                              setAutoCompleteIndex(null);
                            }
                          }
                        }}
                        autoFocus
                        placeholder="Enter a quick start message... (type @ to attach files)"
                        className="w-full border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-black/10 focus:border-gray-400"
                      />
                    ) : (
                      <div
                        className="w-full border border-gray-300 px-3 py-1.5 text-sm cursor-text hover:border-gray-400 transition-colors min-h-[38px] flex items-center flex-wrap gap-0.5"
                        onClick={() => {
                          setEditingMsgIndex(index);
                          requestAnimationFrame(() => {
                            const input = quickStartInputRefs.current[index];
                            input?.focus();
                          });
                        }}
                      >
                        {msg ? (
                          hasFileRefs ? (
                            parseQuickStartMessage(msg).map((seg, si) =>
                              seg.type === 'text' ? (
                                <span key={si} className="text-gray-800">{seg.value}</span>
                              ) : (
                                <span key={si} className="inline-flex items-center gap-1 px-1.5 py-1 bg-orange-50 border border-orange-200/60 text-[11px] text-orange-800 font-medium leading-tight">
                                  {getFileIcon(seg.name, false, 13)}
                                  {seg.name}
                                </span>
                              )
                            )
                          ) : (
                            <span className="text-gray-800">{msg}</span>
                          )
                        ) : (
                          <span className="text-gray-400">Enter a quick start message... (type @ to attach files)</span>
                        )}
                      </div>
                    )}
                    {autoCompleteIndex === index && (
                      <div className="absolute left-0 top-full mt-1 z-20 w-full max-h-48 overflow-y-auto bg-white border border-gray-200 shadow-lg">
                        {suggestions.length > 0 ? suggestions.map((asset, si) => (
                          <button
                            key={asset.relative_path}
                            type="button"
                            onMouseDown={(e) => {
                              e.preventDefault();
                              insertAutoComplete(index, asset.relative_path);
                            }}
                            className={`flex items-center gap-2 w-full px-3 py-1.5 text-left text-xs transition-colors ${
                              si === autoCompleteHighlight ? 'bg-orange-50 text-orange-800' : 'hover:bg-gray-50 text-gray-700'
                            }`}
                          >
                            {getFileIcon(asset.filename, false, 14)}
                            <span className="truncate">{asset.relative_path}</span>
                            <span className="text-[10px] text-gray-400 flex-shrink-0 ml-auto">{asset.filename}</span>
                          </button>
                        )) : (
                          <div className="px-3 py-2 text-xs text-gray-400">
                            {allBundledFiles.length === 0
                              ? 'Select example files above first'
                              : `No files matching "${autoCompleteQuery}"`}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => setQuickStartMessages(prev => prev.filter((_, i) => i !== index))}
                    className="flex items-center justify-center w-8 h-8 text-gray-400 hover:text-red-500 transition-colors"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
                );
              })}
              {quickStartMessages.length < 5 && (
                <button
                  type="button"
                  onClick={() => {
                    setQuickStartMessages(prev => [...prev, '']);
                    setEditingMsgIndex(quickStartMessages.length);
                  }}
                  className="flex items-center justify-center gap-1.5 w-full py-2 bg-gray-50 hover:bg-gray-100 text-xs text-gray-500 hover:text-gray-700 transition-colors"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Add quick start message
                </button>
              )}
            </div>
          </section>

          {/* Upload progress / Error */}
          {uploadProgress && !error && (
            <div className="flex items-center gap-2 text-xs text-blue-600 bg-blue-50 px-3 py-2">
              {uploading && <Loader2 className="w-3.5 h-3.5 animate-spin flex-shrink-0" />}
              {!uploading && <CheckCircle className="w-3.5 h-3.5 flex-shrink-0" />}
              {uploadProgress}
            </div>
          )}
          {error && (
            <div className="text-xs text-red-600 bg-red-50 px-3 py-2">{error}</div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-100">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <div className="flex items-center gap-2">
            <button
              onClick={handleSaveDraft}
              disabled={submitting || uploading}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Save Draft
            </button>
            {!isPendingOrPublished && (
              <button
                onClick={handleSubmitForReview}
                disabled={submitting || uploading}
                className="flex items-center gap-1.5 px-5 py-2 text-sm font-medium text-white bg-gray-900 hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
                <Send className="w-4 h-4" />
                Submit for Review
              </button>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

function mergeAssets(existing: BundledAsset[], incoming: BundledAsset[]): BundledAsset[] {
  const map = new Map(existing.map(a => [a.relative_path, a]));
  for (const asset of incoming) {
    map.set(asset.relative_path, asset);
  }
  return Array.from(map.values());
}

export default PublishDialog;
