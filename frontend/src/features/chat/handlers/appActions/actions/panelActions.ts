/**
 * Panel Management Actions
 *
 * Control workspace panel visibility and layout modes.
 * These actions directly mutate the useWorkspaceStore, so
 * the React UI re-renders instantly.
 */

import { z } from 'zod';
import appAction from '../registry';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import type { ActivityId } from '@/features/workspace/sidebar/ActivityBar';
import { REMOTE_CONTROL_ENABLED } from '@/config/runtimeEnv';

const VALID_ACTIVITIES: ActivityId[] = [
  'project', 'environment', 'search', 'skills', 'workflow', 'api',
  ...(REMOTE_CONTROL_ENABLED ? ['remote' as ActivityId] : []),
];

appAction.registerAction({
  name: 'setActiveActivity',
  description: 'Switch the left sidebar panel (project/file explorer, environments, search, skills, workflow list, API config, remote control). Pass null to collapse the side panel and show only the activity bar.',
  parameters: z.object({
    activity: z
      .enum(['project', 'environment', 'search', 'skills', 'workflow', 'api', 'remote'])
      .nullable()
      .describe('The activity panel to activate, or null to collapse'),
  }),
  handler: async (args) => {
    const { activity } = args;
    useWorkspaceStore.getState().setActiveActivity(activity);
    return { success: true, data: { activeActivity: activity } };
  },
});

appAction.registerAction({
  name: 'setChatPanelCollapsed',
  description: 'Expand or collapse the right-side chat panel.',
  parameters: z.object({
    collapsed: z.boolean().describe('true to collapse, false to expand'),
  }),
  handler: async (args) => {
    useWorkspaceStore.getState().setChatPanelCollapsed(args.collapsed);
    return { success: true, data: { isChatPanelCollapsed: args.collapsed } };
  },
});

appAction.registerAction({
  name: 'setControlPanelMode',
  description: 'Set the bottom control panel mode: normal (default height), maximized (full height), or collapsed (header only).',
  parameters: z.object({
    mode: z.enum(['normal', 'maximized', 'collapsed']),
  }),
  handler: async (args) => {
    const { mode } = args;
    useWorkspaceStore.getState().setControlPanelMode(mode);
    return { success: true, data: { controlPanelMode: mode } };
  },
});

appAction.registerAction({
  name: 'setViewerFullscreen',
  description: 'Toggle the screen viewer fullscreen mode. When fullscreen, left panel, chat panel, and control panel are hidden.',
  parameters: z.object({
    fullscreen: z.boolean(),
  }),
  handler: async (args) => {
    useWorkspaceStore.getState().setViewerFullscreen(args.fullscreen);
    return { success: true, data: { viewerFullscreen: args.fullscreen } };
  },
});

appAction.registerAction({
  name: 'setSidebarMode',
  description: 'Toggle Electron window sidebar mode. When enabled, only the chat panel is shown in a narrow window.',
  parameters: z.object({
    enabled: z.boolean(),
  }),
  handler: async (args) => {
    useWorkspaceStore.getState().setSidebarMode(args.enabled);
    return { success: true, data: { isSidebarMode: args.enabled } };
  },
});

appAction.registerAction({
  name: 'toggleChatHistory',
  description: 'Show or hide the chat history overlay on the chat panel.',
  parameters: z.object({
    show: z.boolean(),
  }),
  handler: async (args) => {
    useWorkspaceStore.getState().setShowHistory(args.show);
    return { success: true, data: { showHistory: args.show } };
  },
});
