import { useMemo } from 'react';
import { GitBranch } from 'lucide-react';
import { BUILTIN_AGENTS, type AgentConfig } from '../config';
import { useWorkflowList } from '@/features/workflow';

export interface WorkflowCapability {
  workflow_id: string;
  name: string;
  description: string;
}

/**
 * Build the agent dropdown from the user's workflow list.
 *
 * The dropdown shows workflows only (no extra "AI Assistant" item).
 * All requests are routed through the orchestrator endpoint which
 * can run app actions, validate intent, or delegate to the selected
 * workflow.
 *
 * `workflowCapabilities` is exported separately so `useChat` can
 * send the full list to the orchestrator regardless of which
 * workflow the user selected.
 */
export function useChatAgents(): {
  agents: AgentConfig[];
  workflowCapabilities: WorkflowCapability[];
  loading: boolean;
} {
  const { workflows, loading } = useWorkflowList();

  const normalizeName = (name: string) => {
    return (name || '')
      .replace(/\s+/g, '')
      .replace(/（官方）|\(官方\)|官方/g, '')
      .replace(/助手/g, '')
      .toLowerCase();
  };

  const officialWorkflowNameSet = useMemo(() => {
    const set = new Set<string>();
    for (const w of workflows || []) {
      if (w?.is_public && /官方/.test(w?.name || '')) {
        set.add(normalizeName(w.name));
      }
    }
    return set;
  }, [workflows]);

  const dynamicWorkflowAgents = useMemo<AgentConfig[]>(() => {
    return (workflows || []).map((w) => {
      const welcomeMessage = w.description
        ? w.description
        : `Please enter your input to start running this workflow.`;

      return {
        id: `workflow:${w.id}`,
        workflow_id: w.id,
        label: w.name,
        desc: w.description || 'My Workflow',
        icon: GitBranch,
        color: 'text-black/60',
        welcomeMessage,
        endpoint: '/api/v1/agent',
      };
    });
  }, [workflows]);

  const workflowCapabilities = useMemo<WorkflowCapability[]>(
    () =>
      (workflows || []).map((w) => ({
        workflow_id: w.id,
        name: w.name,
        description: w.description || '',
      })),
    [workflows],
  );

  const agents = useMemo(() => {
    const visibleBuiltins = BUILTIN_AGENTS.filter(
      (a) => !officialWorkflowNameSet.has(normalizeName(a.label)),
    );
    return [...visibleBuiltins, ...dynamicWorkflowAgents];
  }, [dynamicWorkflowAgents, officialWorkflowNameSet]);

  return { agents, workflowCapabilities, loading };
}
