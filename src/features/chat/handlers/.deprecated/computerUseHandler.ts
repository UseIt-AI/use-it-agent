/**
 * @deprecated 此文件已废弃，功能已被 clientRequestHandler.ts 覆盖
 * 
 * 原功能：处理 computer_use 命令 - 发送电脑控制指令到本地引擎
 * 
 * 废弃原因：
 * - 此 handler 没有被任何地方调用
 * - clientRequestHandler.ts 中的 handleExecuteActions() 已经实现了相同功能
 * - clientRequestHandler 还支持回调机制，功能更完整
 * 
 * 适配新版 Computer API:
 * - POST /api/v1/computer/step  执行操作（主入口）
 * - 请求体: { actions: [...], return_screenshot: boolean }
 * - 响应体: { success: boolean, data: { action_results: [...], screenshot?: string } }
 */

import { CommandHandlerContext, CommandEvent } from '../types';

export function handleComputerUseCommand(
  event: CommandEvent,
  ctx: CommandHandlerContext,
  processedActionsRef: React.MutableRefObject<Set<string>>
): void {
  const { botMessageId, setMessages, localEngineUrl } = ctx;
  
  const cuData = event.data || {};
  const actions = cuData.actions || cuData;
  // 是否需要返回截图（默认 false，如果 actions 中包含 screenshot 类型则自动处理）
  const returnScreenshot = cuData.return_screenshot ?? false;

  // 生成一个唯一标识，用于去重
  const actionKey = JSON.stringify(actions);
  
  // 检查是否已经处理过这个动作
  if (processedActionsRef.current.has(actionKey)) {
    return;
  }
  
  processedActionsRef.current.add(actionKey);
  
  // 先更新消息
  setMessages((prev) => prev.map(msg => 
    msg.id === botMessageId 
      ? { ...msg, content: msg.content + '\n\n💻 已发送电脑控制指令到本地引擎...' }
      : msg
  ));
  
  // 副作用：发送 computer_use 请求到新 API
  fetch(`${localEngineUrl}/api/v1/computer/step`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ 
      actions,
      return_screenshot: returnScreenshot
    })
  })
  .then(res => {
    if (!res.ok) throw new Error('Local computer-use engine error');
    return res.json();
  })
  .then(data => {
    // 处理截图结果
    try {
      const screenshots: string[] = [];
      
      // 1. 检查 return_screenshot 返回的截图
      if (data?.data?.screenshot) {
        screenshots.push(data.data.screenshot);
      }
      
      // 2. 检查 action_results 中的截图（兼容 actions 中包含 screenshot 类型的情况）
      const actionResults = data?.data?.action_results;
      if (Array.isArray(actionResults)) {
        for (const r of actionResults) {
          const result = r?.result;
          if (r?.ok && result?.type === 'screenshot' && result.image_base64) {
            screenshots.push(result.image_base64);
          }
        }
      }
      
      if (screenshots.length > 0) {
        setMessages(current => current.map(m =>
          m.id === botMessageId
            ? {
                ...m,
                details: {
                  ...(m.details || {}),
                  screenshots,
                },
              }
            : m
        ));
      }
    } catch (e) {
      // ignore processing errors
    }
  })
  .catch(() => {
    setMessages(current => current.map(m =>
      m.id === botMessageId
        ? { ...msg, content: m.content + '\n\n⚠️ 本地 Computer Use 引擎连接失败，请确保已启动。' }
        : m
    ));
  });
}
