/**
 * System / Desktop Actions
 *
 * 本文件曾经分出 2 个独立 tool（activate_window / launch_app），现在压缩成
 * 2 个按"动词域"聚合的工具：
 *
 *   - window_control:   窗口的查询 + 所有状态/布局操作
 *   - process_control:  进程/软件的查询 + 启动
 *
 * 压缩动机：主工具总数有 ~20 的软上限，避免 function-call 准确率下滑。
 * action 字段作为 discriminator，现代 LLM 对这种 pattern 很稳。
 *
 * 底层走用户本机的 local-engine（/api/v1/system/window-control 与
 * /api/v1/system/process-control）。前端只做透传 + schema 约束。
 *
 * AI 用到的上下文（都在 prompt 的 "## Current Environment State" 里）:
 * - open_windows: 每行带 `hwnd=... pid=... <process>`，window_control 里的
 *   hwnd 可直接抄。
 * - installed_apps: process_control action="launch" 的 name 参数来源池。
 */

import { z } from 'zod';
import appAction from '../registry';
import { windowControl, processControl } from '@/api/localEngine';

// ==================== window_control ====================

const WINDOW_ACTIONS = [
  'list',
  'get_foreground',
  'list_monitors',
  'activate',
  'minimize',
  'maximize',
  'restore',
  'close',
  'set_topmost',
  'move_resize',
  'tile',
  'capture',
] as const;

appAction.registerAction({
  name: 'window_control',
  description:
    'Unified tool for all desktop window operations. Use the `action` field to pick what to do. ' +
    'This ONE tool replaces a whole family of per-verb tools (minimize_window / maximize_window / ...).\n\n' +
    '## Actions\n' +
    '  • list            — list top-level windows. Optional: process_name, title_contains, include_minimized.\n' +
    '  • get_foreground  — return the currently foreground window.\n' +
    '  • list_monitors   — list displays with work-areas (use their `id` with action=tile).\n' +
    '  • activate        — bring a window to foreground (Alt-Tab equivalent).\n' +
    '  • minimize / maximize / restore — window state.\n' +
    '  • close           — close the window. Optional: force=true to hard-kill (no save prompt).\n' +
    '  • set_topmost     — require `on: boolean` (true = pin on top).\n' +
    '  • move_resize     — require `x, y, width, height`.\n' +
    '  • tile            — arrange multiple windows. Require `hwnds: [int]` + (`layout` OR `zones`). See §Tile.\n' +
    '  • capture         — screenshot at different scopes (without stealing focus). See §Capture.\n\n' +
    '## Targeting a window (single-window actions)\n' +
    'Pass `hwnd` (strongly preferred, copy it from the "### open_windows" environment section). ' +
    'If you don\'t have an hwnd, use `process_name` + `title_contains` for fuzzy match. ' +
    'If multiple match, the response returns `candidates` with hwnds for you to retry.\n\n' +
    '## Tile layouts (comprehensive catalog)\n\n' +
    '**Single-window snap presets** (n=1; extra hwnds go to `skipped`):\n' +
    '  full | left_half | right_half | top_half | bottom_half |\n' +
    '  top_left | top_right | bottom_left | bottom_right | center\n\n' +
    '**Even splits** (N windows, all same size; support `ratios` for asymmetric):\n' +
    '  left_right (2)          — side-by-side\n' +
    '  top_bottom (2)          — stacked\n' +
    '  vertical_3 (3)          — 3 columns\n' +
    '  horizontal_3 (3)        — 3 rows\n' +
    '  vertical_n (N=hwnds)    — N columns\n' +
    '  horizontal_n (N=hwnds)  — N rows\n\n' +
    '**Grids** (uniform grid; does NOT support ratios):\n' +
    '  grid_2x2 (up to 4) | grid_2x3 (up to 6) | grid_3x2 (up to 6) | grid_3x3 (up to 9)\n\n' +
    '**Main + stack** (hwnds[0] is the main/big one, rest stacked; `ratios` is [main, stack], default [2,1]):\n' +
    '  main_left   — hwnds[0] big on LEFT, rest stacked vertically on right\n' +
    '  main_right  — hwnds[0] big on RIGHT, rest stacked vertically on left\n' +
    '  main_top    — hwnds[0] big on TOP, rest stacked horizontally at bottom\n' +
    '  main_bottom — hwnds[0] big at BOTTOM, rest stacked horizontally on top\n\n' +
    '**auto** — picks based on n: 1=full, 2=left_right, 3=vertical_3, 4=grid_2x2, 5-6=grid_3x2, 7-9=grid_3x3, 10+=vertical_n.\n\n' +
    '## Asymmetric proportions via `ratios`\n' +
    'For even splits and main_*: pass a list whose sum does not need to be 1 (auto-normalized). ' +
    'Integers or decimals both work: `[4, 1]` = `[0.8, 0.2]` = 80/20. ' +
    'Length rule: even splits → equal to hwnds length; main_* → exactly 2 ([main, stack]).\n\n' +
    '## Custom zones (ultimate flexibility)\n' +
    'Pass `zones: [{x, y, width, height}, ...]` — each value is a 0~1 proportion of the work area. ' +
    'Length should equal hwnds. Order maps hwnd[i] → zones[i]. When zones is present, layout/ratios are ignored.\n\n' +
    '## Multi-monitor\n' +
    'Call action="list_monitors" first to get monitor ids & work-areas, then pass `monitor_id` to target a specific display.\n\n' +
    '## Capture (screenshots)\n' +
    'Take screenshots at three scopes. **NEVER steals user focus** (critical for cross-app collaboration — ' +
    'the user might be typing in another window when you call this).\n\n' +
    '  • scope="window"      — single window. Locate via `hwnd` / `process_name` / `title_contains`. ' +
    'Uses ImageGrab when window is visible, PrintWindow when obscured/minimized. Best detail-to-size ratio.\n' +
    '  • scope="monitor"     — full display. Captures EVERYTHING on that screen (including other apps). ' +
    'Use this for cross-app collaboration: user has PPT + Word side-by-side, you want to see both. ' +
    'Default = monitor containing the window you specify (via hwnd/process_name/title_contains), ' +
    'or `monitor_id` if explicit, or primary monitor.\n' +
    '  • scope="all_screens" — full virtual desktop across all monitors.\n\n' +
    'Optional params for scope=window:\n' +
    '  • prefer_printwindow: true — force PrintWindow even if window is visible (needed when the target window is ' +
    'partially hidden behind others; slightly less quality but no occlusion artifacts).\n\n' +
    'Response contains: `image_data` (base64 PNG/JPEG), `width`, `height`, `compressed_size_kb`, `context` (hwnd/title/monitor_id).\n\n' +
    '## Examples\n' +
    '  {"action": "minimize", "hwnd": 3081918}\n' +
    '  {"action": "set_topmost", "hwnd": 3081918, "on": true}\n' +
    '  // 左右并排 50/50\n' +
    '  {"action": "tile", "hwnds": [PPT, Word], "layout": "left_right"}\n' +
    '  // PPT 80% + UseIt 20%\n' +
    '  {"action": "tile", "hwnds": [PPT, UseIt], "layout": "left_right", "ratios": [4, 1]}\n' +
    '  // 把 PPT 贴右半屏\n' +
    '  {"action": "tile", "hwnds": [PPT], "layout": "right_half"}\n' +
    '  // IDE 为 main（左 70%），terminal + browser 堆右侧\n' +
    '  {"action": "tile", "hwnds": [IDE, term, browser], "layout": "main_left", "ratios": [7, 3]}\n' +
    '  // 9 宫格排 9 个窗口\n' +
    '  {"action": "tile", "hwnds": [h1,h2,h3,h4,h5,h6,h7,h8,h9], "layout": "grid_3x3"}\n' +
    '  // 完全自定义：PPT 占左上 60%×70%，UseIt 占右侧 40%×100%\n' +
    '  {"action": "tile", "hwnds": [PPT, UseIt], "zones": [\n' +
    '    {"x": 0,   "y": 0, "width": 0.6, "height": 0.7},\n' +
    '    {"x": 0.6, "y": 0, "width": 0.4, "height": 1.0}\n' +
    '  ]}\n' +
    '  // 只截 PowerPoint 窗口（默认；不抢焦点）\n' +
    '  {"action": "capture", "scope": "window", "hwnd": 3081918}\n' +
    '  // 跨软件协作：截 PPT 所在的整块屏幕（看到旁边的 Word/浏览器参考资料）\n' +
    '  {"action": "capture", "scope": "monitor", "hwnd": 3081918}\n' +
    '  // 看多屏整个桌面\n' +
    '  {"action": "capture", "scope": "all_screens"}\n' +
    '  // 窗口被遮挡仍想截到它本身\n' +
    '  {"action": "capture", "scope": "window", "hwnd": 3081918, "prefer_printwindow": true}\n',
  parameters: z
    .object({
      action: z
        .enum(WINDOW_ACTIONS)
        .describe('Which operation to perform; see tool description.'),

      // Targeting (single-window actions)
      hwnd: z.number().int().positive().optional().describe('Window handle from open_windows.'),
      process_name: z.string().optional().describe('Process exe name (case-insensitive), e.g. "POWERPNT.EXE".'),
      title_contains: z.string().optional().describe('Case-insensitive substring of window title.'),

      // list
      include_minimized: z
        .boolean()
        .optional()
        .describe('action=list only: include minimized windows. Default true.'),

      // set_topmost
      on: z.boolean().optional().describe('action=set_topmost only: true pin / false unpin.'),

      // move_resize
      x: z.number().int().optional(),
      y: z.number().int().optional(),
      width: z.number().int().positive().optional(),
      height: z.number().int().positive().optional(),

      // tile
      hwnds: z
        .array(z.number().int().positive())
        .optional()
        .describe('action=tile only: windows to arrange; order = placement order.'),
      layout: z
        .enum([
          'auto',
          // single-window snap
          'full',
          'left_half', 'right_half', 'top_half', 'bottom_half',
          'top_left', 'top_right', 'bottom_left', 'bottom_right',
          'center',
          // even splits
          'left_right', 'top_bottom',
          'vertical_3', 'horizontal_3',
          'vertical_n', 'horizontal_n',
          // grids
          'grid_2x2', 'grid_2x3', 'grid_3x2', 'grid_3x3',
          // main + stack
          'main_left', 'main_right', 'main_top', 'main_bottom',
        ])
        .optional()
        .describe('action=tile only: layout strategy. Default "auto". See tool description for full catalog.'),
      monitor_id: z
        .number()
        .int()
        .positive()
        .optional()
        .describe('action=tile only: target monitor id (from list_monitors). Default primary.'),
      ratios: z
        .array(z.number().positive())
        .optional()
        .describe(
          'action=tile only: asymmetric split ratios. ' +
            'For even splits (left_right / top_bottom / vertical_3 / horizontal_3 / vertical_n / horizontal_n): length MUST equal hwnds length. ' +
            'For main_* layouts: length MUST be exactly 2 ([main, stack]). ' +
            'Integers or decimals both accepted (auto-normalized). ' +
            'e.g. [4, 1] or [0.8, 0.2] = 80/20.',
        ),
      zones: z
        .array(
          z.object({
            x: z.number().min(0).max(1),
            y: z.number().min(0).max(1),
            width: z.number().gt(0).max(1),
            height: z.number().gt(0).max(1),
          }),
        )
        .optional()
        .describe(
          'action=tile only: custom rectangles (overrides layout/ratios). ' +
            'Each {x,y,width,height} is a 0~1 proportion of the work area. ' +
            'Length should equal hwnds; order maps hwnd[i] → zones[i]. ' +
            'e.g. left 80% + right 20%: [{x:0,y:0,width:0.8,height:1},{x:0.8,y:0,width:0.2,height:1}]',
        ),

      // close
      force: z
        .boolean()
        .optional()
        .describe('action=close only: force=true kills process (no save prompt). Default false.'),

      // capture
      scope: z
        .enum(['window', 'monitor', 'all_screens'])
        .optional()
        .describe(
          'action=capture only: "window" (default, locate via hwnd/process_name/title_contains), ' +
            '"monitor" (entire display; captures all apps on that screen — use for cross-app collaboration), ' +
            '"all_screens" (full virtual desktop across all monitors).',
        ),
      prefer_printwindow: z
        .boolean()
        .optional()
        .describe(
          'action=capture scope=window only: force PrintWindow path (for when target window is obscured). ' +
            'Default false = use ImageGrab (best quality for visible windows).',
        ),
      compress: z
        .boolean()
        .optional()
        .describe('action=capture only: compress output to ~300KB. Default true.'),
    })
    .superRefine((d, ctx) => {
      // 按 action 做交叉校验，AI 传了错的组合能尽早拿到明确错误
      const singleTargetRequired = new Set<(typeof WINDOW_ACTIONS)[number]>([
        'activate', 'minimize', 'maximize', 'restore', 'close', 'set_topmost', 'move_resize',
      ]);
      if (singleTargetRequired.has(d.action as any)) {
        const hasTarget =
          d.hwnd !== undefined ||
          (d.process_name && d.process_name.trim().length > 0) ||
          (d.title_contains && d.title_contains.trim().length > 0);
        if (!hasTarget) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: `action="${d.action}" requires one of: hwnd, process_name, title_contains`,
          });
        }
      }
      if (d.action === 'set_topmost' && typeof d.on !== 'boolean') {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['on'],
          message: 'action="set_topmost" requires `on: boolean`',
        });
      }
      if (d.action === 'move_resize') {
        const missing = ['x', 'y', 'width', 'height'].filter(
          (k) => (d as any)[k] === undefined,
        );
        if (missing.length > 0) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: `action="move_resize" requires: ${missing.join(', ')}`,
          });
        }
      }
      if (d.action === 'tile') {
        if (!d.hwnds || d.hwnds.length === 0) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ['hwnds'],
            message: 'action="tile" requires non-empty `hwnds`',
          });
        }
        // zones 和 ratios 互斥
        if (d.zones && d.ratios) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ['zones'],
            message: '`zones` and `ratios` are mutually exclusive; zones ignores layout/ratios',
          });
        }
        // zones 长度应等于 hwnds
        if (d.zones && d.hwnds && d.zones.length !== d.hwnds.length) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ['zones'],
            message: `zones length (${d.zones.length}) must equal hwnds length (${d.hwnds.length})`,
          });
        }
        // ratios 长度规则：main_* => 2；其它 => 等于 hwnds
        if (d.ratios && d.hwnds) {
          const layout = d.layout || 'auto';
          const isMainStack = layout.startsWith('main_');
          const expected = isMainStack ? 2 : d.hwnds.length;
          if (d.ratios.length !== expected) {
            ctx.addIssue({
              code: z.ZodIssueCode.custom,
              path: ['ratios'],
              message: isMainStack
                ? `for layout=${layout}, ratios must be exactly 2 elements ([main, stack]); got ${d.ratios.length}`
                : `ratios length (${d.ratios.length}) must equal hwnds length (${d.hwnds.length})`,
            });
          }
        }
      }
      if (d.action === 'capture') {
        const s = d.scope || 'window';
        if (s === 'window') {
          const hasTarget =
            d.hwnd !== undefined ||
            (d.process_name && d.process_name.trim().length > 0) ||
            (d.title_contains && d.title_contains.trim().length > 0);
          if (!hasTarget) {
            ctx.addIssue({
              code: z.ZodIssueCode.custom,
              message: 'action="capture" scope="window" requires one of: hwnd, process_name, title_contains',
            });
          }
        }
      }
    }),
  handler: async (args) => {
    const result = await windowControl(args as any);
    if (result.success) {
      // 把各 action 的主要信息摊平出来，UI 展示和后续 AI 决策都更好用
      return {
        success: true,
        data: {
          action: args.action,
          window: result.window,
          windows: result.windows,
          monitors: result.monitors,
          placed: result.placed,
          skipped: result.skipped,
          errors: result.errors,
          hwnd: result.hwnd,
          title: result.title,
          is_foreground: result.is_foreground,
          // capture action
          scope: result.scope,
          image_data: result.image_data,
          width: result.width,
          height: result.height,
          compressed_size_kb: result.compressed_size_kb,
          context: result.context,
          warning: result.warning ?? undefined,
        },
      };
    }
    const detail =
      result.error ||
      result.warning ||
      (result.candidates && result.candidates.length > 0
        ? `multiple windows matched (${result.candidates.length}); pick a specific hwnd and retry`
        : `window_control (action=${args.action}) failed`);
    return {
      success: false,
      error: detail,
      data: {
        action: args.action,
        warning: result.warning,
        candidates: result.candidates,
        criteria: result.criteria,
      },
    };
  },
});

// ==================== process_control ====================

const PROCESS_ACTIONS = [
  'launch',
  'find_exe',
  'list_installed',
  'list_processes',
  'get_process',
] as const;

appAction.registerAction({
  name: 'process_control',
  description:
    'Unified tool for launching apps / opening files and querying installed software & running processes. ' +
    'Use the `action` field to pick what to do.\n\n' +
    'Supported actions:\n' +
    '  • launch          — launch app / open file. Require ONE of: name / file / exe_path.\n' +
    '                      Patterns:\n' +
    '                        {action:"launch", name:"PowerPoint"}\n' +
    '                        {action:"launch", file:"C:/tmp/deck.pptx"}\n' +
    '                        {action:"launch", name:"PowerPoint", file:"C:/tmp/deck.pptx"}\n' +
    '                        {action:"launch", exe_path:"C:/.../POWERPNT.EXE", args:[...]}\n' +
    '                      BEFORE calling launch, consult "### installed_apps" for a valid `name`. If the ' +
    '                      target is ALREADY in open_windows, call window_control action="activate" instead.\n' +
    '  • find_exe        — fuzzy search launchable exe by name. Require `name`.\n' +
    '  • list_installed  — list installed software. Optional `name` (substring filter).\n' +
    '  • list_processes  — list running processes. Optional `name_contains`, `include_system`, `include_metrics`.\n' +
    '  • get_process     — per-pid process detail. Require `pid`.\n',
  parameters: z
    .object({
      action: z.enum(PROCESS_ACTIONS).describe('Which operation to perform.'),

      // launch / find_exe / list_installed
      name: z.string().optional().describe('Software display name for launch/find_exe/list_installed.'),
      file: z.string().optional().describe('action=launch only: absolute file path to open.'),
      exe_path: z.string().optional().describe('action=launch only: absolute path to an executable.'),
      args: z
        .array(z.string())
        .optional()
        .describe('action=launch only: command-line args. Each element MUST be a plain string.'),
      cwd: z.string().optional().describe('action=launch only: working directory.'),

      // list_processes
      name_contains: z.string().optional().describe('action=list_processes only: exe-name substring.'),
      include_system: z
        .boolean()
        .optional()
        .describe('action=list_processes only: include svchost etc. Default false.'),
      include_metrics: z
        .boolean()
        .optional()
        .describe('action=list_processes only: collect CPU/memory (extra cost). Default false.'),

      // get_process
      pid: z.number().int().positive().optional().describe('action=get_process only: target pid.'),
    })
    .superRefine((d, ctx) => {
      if (d.action === 'launch' && !(d.name || d.file || d.exe_path)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'action="launch" requires one of: name, file, exe_path',
        });
      }
      if (d.action === 'find_exe' && !d.name) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['name'],
          message: 'action="find_exe" requires `name`',
        });
      }
      if (d.action === 'get_process' && d.pid === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['pid'],
          message: 'action="get_process" requires `pid`',
        });
      }
    }),
  handler: async (args) => {
    const result = await processControl(args as any);
    if (result.success) {
      return {
        success: true,
        data: {
          action: args.action,
          pid: result.pid,
          exe: result.exe,
          file: result.file,
          launched_via: result.launched_via,
          matched_software: result.matched_software,
          note: result.note,
          candidates: result.candidates,
          software: result.software,
          processes: result.processes,
        },
      };
    }
    return {
      success: false,
      error: result.error || `process_control (action=${args.action}) failed`,
    };
  },
});
