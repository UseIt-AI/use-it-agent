/**
 * Environment & VM Actions
 *
 * AI-invocable actions for managing environments (This PC / VM),
 * querying VM info (specs, agent status, installed software),
 * and switching the active workflow.
 *
 * - Environment config is stored in Electron app config.
 * - Agent status and installed software are queried via HTTP to the
 *   local_engine running inside each VM (port 8324), which is fast (~100-200ms).
 * - VM hardware specs are queried via Electron IPC (Hyper-V PowerShell, ~1-2s).
 */
import { z } from 'zod';
import appAction from '../registry';
import { workflowApi } from '@/features/workflow/api';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';

const LOCAL_ENGINE_PORT = 8324;
async function getElectron() {
  if (!window.electron) {
    throw new Error('Electron API not available (web mode)');
  }
  return window.electron;
}


// ==================== Environment Config ====================
appAction.registerAction({
  name: 'listEnvironments',
  description: 'List all configured environments (This PC and VMs). Returns id, type, name, and vmName for each.',
  handler: async () => {
    const electron = await getElectron();
    if (!electron.getAppConfig) throw new Error('getAppConfig not available');
    const config = await electron.getAppConfig();
    const envs = (config?.environments as any[]) || [];
    const hasLocal = envs.some((e: any) => e.id === 'local' || e.type === 'local');
    const list = hasLocal ? envs : [{ id: 'local', type: 'local', name: 'This PC' }, ...envs];
    return {
      success: true,
      data: list.map((e: any) => ({
        id: e.id,
        type: e.type,
        name: e.name,
        vmName: e.vmName || null,
      })),
    };
  },
});

appAction.registerAction({
  name: 'getActiveEnvironment',
  description: 'Get the currently active environment (agent target). Returns its id, type, name.',
  handler: async () => {
    const activeId = useWorkspaceStore.getState().activeTargetId || 'local';
    let envs: any[] = [];
    if (window.electron?.getAppConfig) {
      envs = (await window.electron.getAppConfig('environments')) || [];
    }
    const active = envs.find((e: any) => e.id === activeId) ||
      { id: 'local', type: 'local', name: 'This PC' };
    return {
      success: true,
      data: {
        id: active.id ?? activeId,
        type: active.type ?? 'local',
        name: active.name ?? activeId,
        vmName: active.vmName || null,
      },
    };
  },
});

appAction.registerAction({
  name: 'setActiveEnvironment',
  description: 'Switch the active environment (agent target). Use the environment id (e.g. "local" for This PC, or a VM id).',
  parameters: z.object({
    environmentId: z.string().describe('The environment id to activate'),
  }),
  handler: async (args) => {
    let envs: any[] = [];
    if (window.electron?.getAppConfig) {
      envs = (await window.electron.getAppConfig('environments')) || [];
    }
    const target = envs.find((e: any) => e.id === args.environmentId);
    if (!target && args.environmentId !== 'local') {
      return { success: false, error: `Environment not found: ${args.environmentId}. Use listEnvironments to see available IDs.` };
    }
    useWorkspaceStore.getState().setActiveTargetId(args.environmentId);
    window.dispatchEvent(new Event('environments-updated'));
    const name = target?.name || (args.environmentId === 'local' ? 'This PC' : args.environmentId);
    return { success: true, data: { activeEnvironmentId: args.environmentId, name } };
  },
});


// ==================== Workflow Switch ====================
appAction.registerAction({
  name: 'switchWorkflow',
  description: 'Switch to a workflow by name (fuzzy) or by ID. Opens it in the editor if not already open.',
  parameters: z.object({
    name: z.string().describe('Workflow name to search for (case-insensitive partial match)').optional(),
    workflowId: z.string().describe('Workflow ID (exact). Takes priority over name if both provided.').optional(),
  }),
  handler: async (args) => {
    let targetId = args.workflowId;
    let targetName = '';
    if (!targetId && args.name) {
      const workflows = await workflowApi.list();
      const query = args.name.toLowerCase();
      const match = workflows.find((w) => w.name.toLowerCase() === query)
        || workflows.find((w) => w.name.toLowerCase().includes(query));
      if (!match) {
        return {
          success: false,
          error: `No workflow found matching "${args.name}". Available: ${workflows.map((w) => w.name).join(', ')}`,
        };
      }
      targetId = match.id;
      targetName = match.name;
    }
    if (!targetId) {
      return { success: false, error: 'Provide either name or workflowId' };
    }
    window.dispatchEvent(
      new CustomEvent('app-action:open-workflow', { detail: { workflowId: targetId } })
    );
    return { success: true, data: { workflowId: targetId, name: targetName || targetId } };
  },
});

