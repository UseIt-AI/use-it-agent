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
import { VM_ENABLED } from '@/config/runtimeEnv';

const LOCAL_ENGINE_PORT = 8324;
async function getElectron() {
  if (!window.electron) {
    throw new Error('Electron API not available (web mode)');
  }
  return window.electron;
}

async function resolveVmIp(vmName: string): Promise<string> {
  const electron = await getElectron();
  if (!electron.getVmIp) throw new Error('getVmIp not available');
  const ip = await electron.getVmIp(vmName);
  if (!ip) throw new Error(`Could not resolve IP for VM: ${vmName}`);
  return ip;
}

async function fetchLocalEngine(vmIp: string, path: string, timeoutMs = 5000): Promise<any> {
  const url = `http://${vmIp}:${LOCAL_ENGINE_PORT}${path}`;
  const response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
  if (!response.ok) {
    throw new Error(`local_engine returned ${response.status}: ${response.statusText}`);
  }
  return response.json();
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

// ==================== VM-specific actions (gated by VITE_ENABLE_VM) ====================
if (VM_ENABLED) {

appAction.registerAction({
  name: 'getVmSpecs',
  description: 'Get hardware specs of a VM (CPU, RAM, disk, state, uptime). Requires the VM name.',
  parameters: z.object({
    vmName: z.string().describe('The Hyper-V VM name'),
  }),
  handler: async (args) => {
    const electron = await getElectron();
    if (!electron.getVmSpecs) throw new Error('getVmSpecs not available');
    const specs = await electron.getVmSpecs(args.vmName);
    return { success: true, data: specs };
  },
});

appAction.registerAction({
  name: 'getAgentStatus',
  description: 'Check if the UseIt agent (local_engine) is running on a VM and get its version. Fast HTTP check (~100-200ms when agent is online).',
  parameters: z.object({
    vmName: z.string().describe('The Hyper-V VM name'),
  }),
  handler: async (args) => {
    try {
      const ip = await resolveVmIp(args.vmName);
      const health = await fetchLocalEngine(ip, '/health', 3000);
      return {
        success: true,
        data: {
          running: true,
          status: health.status,
          version: health.version,
          pid: health.pid,
          controllers: health.controllers,
          vmIp: ip,
        },
      };
    } catch (err: any) {
      return {
        success: true,
        data: {
          running: false,
          error: err.message || String(err),
        },
      };
    }
  },
});

appAction.registerAction({
  name: 'getVmInstalledSoftware',
  description: 'Get the list of software installed on a VM. Requires the agent to be running. Fast HTTP query (~100-200ms).',
  parameters: z.object({
    vmName: z.string().describe('The Hyper-V VM name'),
  }),
  handler: async (args) => {
    try {
      const ip = await resolveVmIp(args.vmName);
      const result = await fetchLocalEngine(ip, '/api/v1/installed-software', 5000);
      return {
        success: true,
        data: {
          vmName: args.vmName,
          count: result.count,
          software: result.software,
        },
      };
    } catch (err: any) {
      return {
        success: false,
        error: `Failed to query installed software. Is the agent running on ${args.vmName}? Error: ${err.message}`,
      };
    }
  },
});

// ==================== VM Setup & Installation ====================
appAction.registerAction({
  name: 'getVmSetupStatus',
  description: `Get the full VM setup status. Returns the current stage of the setup pipeline so the AI can decide what action to take next. Possible stages:
- unsupported_system: Windows Home edition, cannot use Hyper-V
- no_hyperv: Hyper-V not enabled → use enableHyperV
- permission_required: Need Hyper-V admin permission → use fixHyperVPermission
- no_vm: Hyper-V ready but no VM exists → use installVm or restoreVmFromFolder
- ready: VM exists → check agent status with getAgentStatus
Also returns disk space, system info, and whether the VM exists.`,
  parameters: z.object({
    vmName: z.string().describe('VM name pattern to check (default: UseIt-Dev-VM)').optional(),
    installDir: z.string().describe('Install directory to check disk space (default: C:\\VMs)').optional(),
  }),
  handler: async (args) => {
    const electron = await getElectron();
    const vmNamePattern = args.vmName || 'UseIt-Dev-VM';
    const result: Record<string, any> = { vmNamePattern };
    // Step 0: System check
    if (electron.vmCheckEnvironment) {
      try {
        const env = await electron.vmCheckEnvironment(args.installDir);
        result.environment = env;
        if (!env.isProOrEnterprise) {
          result.stage = 'unsupported_system';
          result.message = `System does not support Hyper-V (${env.windowsVersion || 'Home edition'})`;
          return { success: true, data: result };
        }
      } catch { /* fallthrough */ }
    }
    // Step 1: Hyper-V
    let hyperVEnabled = false;
    if (electron.checkHyperVEnabled) {
      try {
        hyperVEnabled = await electron.checkHyperVEnabled();
      } catch (e: any) {
        if (!e.message?.includes('not available')) {
          const msg = (e.message || '').toLowerCase();
          if (msg.includes('get-vm') && (msg.includes('not recognized') || msg.includes('commandnotfound'))) {
            result.stage = 'no_hyperv';
            result.message = 'Hyper-V feature is not enabled';
            return { success: true, data: result };
          }
          if (msg.includes('permission') || msg.includes('access') || msg.includes('denied')) {
            result.stage = 'permission_required';
            result.message = 'Hyper-V permission required';
            return { success: true, data: result };
          }
        }
        hyperVEnabled = true;
      }
    }
    result.hyperVEnabled = hyperVEnabled;
    if (!hyperVEnabled) {
      result.stage = 'no_hyperv';
      result.message = 'Hyper-V is not enabled. Use enableHyperV to enable it.';
      return { success: true, data: result };
    }
    // Step 2: VM exists?
    if (electron.checkVmExists) {
      try {
        const vmResult = await electron.checkVmExists(vmNamePattern);
        result.vmExists = vmResult.exists;
        result.vmName = vmResult.vmName;
      } catch (e: any) {
        const msg = (e.message || '').toLowerCase();
        if (msg.includes('permission') || msg.includes('access') || msg.includes('denied')) {
          result.stage = 'permission_required';
          result.message = 'Hyper-V administrator permission required. Use fixHyperVPermission.';
          return { success: true, data: result };
        }
        result.vmExists = false;
      }
    }
    if (!result.vmExists) {
      result.stage = 'no_vm';
      result.message = 'Hyper-V is ready but no VM found. Use installVm or restoreVmFromFolder to create one.';
      return { success: true, data: result };
    }
    // Step 3: VM power state
    if (electron.getVmStatus && result.vmName) {
      try {
        result.vmPowerState = await electron.getVmStatus(result.vmName);
      } catch { /* ignore */ }
    }
    result.stage = 'ready';
    result.message = 'VM exists and Hyper-V is ready.';
    return { success: true, data: result };
  },
});

appAction.registerAction({
  name: 'enableHyperV',
  description: 'Enable the Hyper-V feature on Windows. May require a system reboot to complete. Requires admin/UAC elevation.',
  handler: async () => {
    const electron = await getElectron();
    if (!electron.vmEnableHyperV) throw new Error('vmEnableHyperV not available');
    const result = await electron.vmEnableHyperV();
    if (!result.success) {
      return { success: false, error: 'Failed to enable Hyper-V. Check if running as admin.' };
    }
    return {
      success: true,
      data: {
        needsReboot: result.needsReboot,
        message: result.needsReboot
          ? 'Hyper-V has been enabled but a system reboot is required to activate it.'
          : 'Hyper-V has been enabled successfully.',
      },
    };
  },
});

appAction.registerAction({
  name: 'fixHyperVPermission',
  description: 'Fix Hyper-V permissions by adding the current user to the Hyper-V Administrators group. Triggers a UAC elevation prompt.',
  handler: async () => {
    const electron = await getElectron();
    if (!electron.fixHyperVPermission) throw new Error('fixHyperVPermission not available');
    await electron.fixHyperVPermission();
    return { success: true, data: { message: 'Hyper-V permissions have been fixed. You may need to sign out and back in.' } };
  },
});

appAction.registerAction({
  name: 'checkVmEnvironment',
  description: 'Check VM environment prerequisites: Hyper-V status, Windows edition, disk space, admin status.',
  parameters: z.object({
    installDir: z.string().describe('Directory to check disk space for (default: C:\\VMs)').optional(),
  }),
  handler: async (args) => {
    const electron = await getElectron();
    if (!electron.vmCheckEnvironment) throw new Error('vmCheckEnvironment not available');
    const result = await electron.vmCheckEnvironment(args.installDir);
    return { success: true, data: result };
  },
});

appAction.registerAction({
  name: 'installVm',
  description: 'Install a new VM from a Windows ISO file. This is a long-running operation (5-15 min). The ISO path must be provided (use a known path, or ask the user). Default install dir is C:\\VMs.',
  parameters: z.object({
    isoPath: z.string().describe('Absolute path to the Windows ISO file'),
    vmName: z.string().describe('Name for the new VM (default: UseIt-Dev-VM)').optional(),
    installDir: z.string().describe('Directory to install the VM in (default: C:\\VMs)').optional(),
    memorySizeGB: z.number().describe('RAM in GB (default: 4)').optional(),
    cpuCount: z.number().describe('Number of CPU cores (default: 4)').optional(),
    diskSizeGB: z.number().describe('Virtual disk size in GB (default: 60)').optional(),
  }),
  handler: async (args) => {
    const electron = await getElectron();
    if (!electron.vmInstall) throw new Error('vmInstall not available');
    if (electron.vmValidateIso) {
      const validation = await electron.vmValidateIso(args.isoPath);
      if (!validation.valid) {
        return { success: false, error: `Invalid ISO file: ${validation.error || 'validation failed'}` };
      }
    }
    const result = await electron.vmInstall({
      isoPath: args.isoPath,
      vmName: args.vmName,
      installDir: args.installDir,
      memorySizeGB: args.memorySizeGB,
      cpuCount: args.cpuCount,
      diskSizeGB: args.diskSizeGB,
    });
    if (!result.success) {
      return { success: false, error: result.error || 'VM installation failed' };
    }
    window.dispatchEvent(new Event('environments-updated'));
    return { success: true, data: { vmName: args.vmName || 'UseIt-Dev-VM', action: 'installed' } };
  },
});

appAction.registerAction({
  name: 'restoreVmFromFolder',
  description: 'Import/restore a VM from an exported VM folder (contains .vmcx or virtual disk files). Faster than installing from ISO.',
  parameters: z.object({
    folderPath: z.string().describe('Absolute path to the exported VM folder'),
    vmName: z.string().describe('Name for the restored VM (optional, auto-detected from export)').optional(),
  }),
  handler: async (args) => {
    const electron = await getElectron();
    if (!electron.vmRestoreFromFolder) throw new Error('vmRestoreFromFolder not available');
    const result = await electron.vmRestoreFromFolder({
      vmName: args.vmName,
      folderPath: args.folderPath,
    });
    if (!result.success) {
      return { success: false, error: result.error || 'VM restore failed' };
    }
    window.dispatchEvent(new Event('environments-updated'));
    return {
      success: true,
      data: {
        vmName: result.vmName || args.vmName,
        checkpointCount: result.checkpointCount,
        restoreMode: result.restoreMode,
        action: 'restored',
      },
    };
  },
});

appAction.registerAction({
  name: 'cancelVmInstall',
  description: 'Cancel an ongoing VM installation.',
  handler: async () => {
    const electron = await getElectron();
    if (!electron.vmInstallCancel) throw new Error('vmInstallCancel not available');
    await electron.vmInstallCancel();
    return { success: true, data: { action: 'cancelled' } };
  },
});

appAction.registerAction({
  name: 'setVmSpecs',
  description: 'Configure VM hardware specs (CPU cores, RAM, dynamic memory). The VM must be turned off first.',
  parameters: z.object({
    vmName: z.string().describe('The Hyper-V VM name'),
    cpuCores: z.number().describe('Number of CPU cores'),
    memoryGB: z.number().describe('Memory in GB'),
    isDynamicMemory: z.boolean().describe('Enable dynamic memory (default: false)').optional(),
  }),
  handler: async (args) => {
    const electron = await getElectron();
    if (!electron.setVmSpecs) throw new Error('setVmSpecs not available');
    await electron.setVmSpecs({
      vmName: args.vmName,
      cpuCores: args.cpuCores,
      memoryGB: args.memoryGB,
      isDynamicMemory: args.isDynamicMemory ?? false,
    });
    return { success: true, data: { vmName: args.vmName, cpuCores: args.cpuCores, memoryGB: args.memoryGB } };
  },
});

appAction.registerAction({
  name: 'ensureVmVnc',
  description: 'Install/verify TightVNC inside a VM for screen viewing. The VM must be running.',
  parameters: z.object({
    vmName: z.string().describe('The Hyper-V VM name'),
  }),
  handler: async (args) => {
    const electron = await getElectron();
    if (!electron.ensureVmVnc) throw new Error('ensureVmVnc not available');
    const result = await electron.ensureVmVnc({
      vmName: args.vmName,
      username: 'useit',
      password: '12345678',
    });
    return {
      success: true,
      data: {
        vmName: result.vmName,
        installed: result.installed,
        alreadyInstalled: result.alreadyInstalled,
      },
    };
  },
});

appAction.registerAction({
  name: 'checkAgentDetailed',
  description: 'Detailed agent status check via Electron IPC (serviceCheckStatus). Returns installed/version info. Different from getAgentStatus which uses HTTP.',
  parameters: z.object({
    vmName: z.string().describe('The Hyper-V VM name'),
  }),
  handler: async (args) => {
    const electron = await getElectron();
    const result: Record<string, any> = { vmName: args.vmName };
    if (electron.serviceGetLocalVersion) {
      try {
        const localRes = await electron.serviceGetLocalVersion();
        result.localVersion = localRes.version || null;
      } catch { /* ignore */ }
    }
    if (electron.serviceCheckStatus) {
      const statusRes = await electron.serviceCheckStatus({
        vmName: args.vmName,
        serviceKey: 'local_engine',
      });
      if (statusRes.success) {
        result.agentInstalled = statusRes.status?.installed ?? false;
        result.agentVersion = statusRes.status?.version || null;
        result.agentStatus = result.agentInstalled
          ? (result.localVersion && result.agentVersion && result.localVersion !== result.agentVersion ? 'outdated' : 'up_to_date')
          : 'not_installed';
      } else {
        result.agentStatus = 'error';
        result.error = statusRes.error;
      }
    } else {
      throw new Error('serviceCheckStatus not available');
    }
    return { success: true, data: result };
  },
});

// ==================== VM Lifecycle ====================
appAction.registerAction({
  name: 'getVmStatus',
  description: 'Get the power state of a Hyper-V VM (Running, Off, Paused, etc.).',
  parameters: z.object({
    vmName: z.string().describe('The Hyper-V VM name'),
  }),
  handler: async (args) => {
    const electron = await getElectron();
    if (!electron.getVmStatus) throw new Error('getVmStatus not available');
    const status = await electron.getVmStatus(args.vmName);
    return { success: true, data: { vmName: args.vmName, status } };
  },
});

appAction.registerAction({
  name: 'startVm',
  description: 'Start a Hyper-V VM. The VM must be in Off or Paused state.',
  parameters: z.object({
    vmName: z.string().describe('The Hyper-V VM name'),
  }),
  handler: async (args) => {
    const electron = await getElectron();
    if (!electron.startVm) throw new Error('startVm not available');
    await electron.startVm(args.vmName);
    window.dispatchEvent(new Event('environments-updated'));
    return { success: true, data: { vmName: args.vmName, action: 'started' } };
  },
});

appAction.registerAction({
  name: 'stopVm',
  description: 'Stop (turn off) a Hyper-V VM immediately.',
  parameters: z.object({
    vmName: z.string().describe('The Hyper-V VM name'),
  }),
  handler: async (args) => {
    const electron = await getElectron();
    if (!electron.stopVm) throw new Error('stopVm not available');
    await electron.stopVm(args.vmName);
    window.dispatchEvent(new Event('environments-updated'));
    return { success: true, data: { vmName: args.vmName, action: 'stopped' } };
  },
});

// ==================== VM Snapshots ====================
appAction.registerAction({
  name: 'listVmSnapshots',
  description: 'List all checkpoints/snapshots for a VM. Returns Id, Name, CreationTime, CheckpointType for each.',
  parameters: z.object({
    vmName: z.string().describe('The Hyper-V VM name'),
  }),
  handler: async (args) => {
    const electron = await getElectron();
    if (!electron.listVmSnapshots) throw new Error('listVmSnapshots not available');
    const snapshots = await electron.listVmSnapshots(args.vmName);
    return { success: true, data: { vmName: args.vmName, snapshots } };
  },
});

appAction.registerAction({
  name: 'createVmSnapshot',
  description: 'Create a new checkpoint/snapshot for a VM.',
  parameters: z.object({
    vmName: z.string().describe('The Hyper-V VM name'),
    snapshotName: z.string().describe('Name for the new snapshot'),
  }),
  handler: async (args) => {
    const electron = await getElectron();
    if (!electron.createVmSnapshot) throw new Error('createVmSnapshot not available');
    await electron.createVmSnapshot({
      vmName: args.vmName,
      snapshotName: args.snapshotName,
      saveState: false,
    });
    return { success: true, data: { vmName: args.vmName, snapshotName: args.snapshotName } };
  },
});

appAction.registerAction({
  name: 'restoreVmSnapshot',
  description: 'Restore a VM to a specific snapshot/checkpoint. Use listVmSnapshots to get the snapshot Id.',
  parameters: z.object({
    vmName: z.string().describe('The Hyper-V VM name'),
    snapshotId: z.string().describe('Snapshot Id (GUID) to restore to'),
  }),
  handler: async (args) => {
    const electron = await getElectron();
    if (!electron.restoreVmSnapshot) throw new Error('restoreVmSnapshot not available');
    await electron.restoreVmSnapshot({
      vmName: args.vmName,
      snapshotId: args.snapshotId,
    });
    window.dispatchEvent(
      new CustomEvent('vm-snapshot-restored', { detail: { vmName: args.vmName, snapshotId: args.snapshotId } })
    );
    return { success: true, data: { vmName: args.vmName, snapshotId: args.snapshotId, action: 'restored' } };
  },
});

// ==================== Agent / Service ====================
appAction.registerAction({
  name: 'deployAgent',
  description: 'Deploy/install the UseIt agent (local_engine + computer_server) into a VM. The VM must be running. Takes ~10-30s.',
  parameters: z.object({
    vmName: z.string().describe('The Hyper-V VM name'),
  }),
  handler: async (args) => {
    const electron = await getElectron();
    if (!electron.serviceDeploy) throw new Error('serviceDeploy not available');
    const result = await electron.serviceDeploy({
      vmName: args.vmName,
      username: 'useit',
      password: '12345678',
    });
    if (result && !result.success) {
      return { success: false, error: result.error || 'Deploy failed' };
    }
    return { success: true, data: { vmName: args.vmName, action: 'deployed' } };
  },
});

appAction.registerAction({
  name: 'restartAgent',
  description: 'Restart the UseIt agent service inside a VM.',
  parameters: z.object({
    vmName: z.string().describe('The Hyper-V VM name'),
  }),
  handler: async (args) => {
    const electron = await getElectron();
    if (!electron.serviceRestart) throw new Error('serviceRestart not available');
    const result = await electron.serviceRestart({ vmName: args.vmName });
    if (result && !result.success) {
      return { success: false, error: result.error || 'Restart failed' };
    }
    return { success: true, data: { vmName: args.vmName, action: 'restarted' } };
  },
});

// ==================== VM Export & Hyper-V ====================
appAction.registerAction({
  name: 'exportVm',
  description: 'Export a VM to a folder on the host machine. The export dir must exist.',
  parameters: z.object({
    vmName: z.string().describe('The Hyper-V VM name'),
    exportDir: z.string().describe('Absolute path to the export destination folder'),
  }),
  handler: async (args) => {
    const electron = await getElectron();
    if (!electron.vmExportToFolder) throw new Error('vmExportToFolder not available');
    const result = await electron.vmExportToFolder({
      vmName: args.vmName,
      exportDir: args.exportDir,
    });
    if (result && !result.success) {
      return { success: false, error: result.error || 'Export failed' };
    }
    return { success: true, data: { vmName: args.vmName, exportPath: result.exportPath } };
  },
});

appAction.registerAction({
  name: 'checkHyperVEnabled',
  description: 'Check if Hyper-V is available and enabled on the host machine.',
  handler: async () => {
    const electron = await getElectron();
    if (!electron.checkHyperVEnabled) throw new Error('checkHyperVEnabled not available');
    const enabled = await electron.checkHyperVEnabled();
    return { success: true, data: { hyperVEnabled: enabled } };
  },
});

} // end VM_ENABLED

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

