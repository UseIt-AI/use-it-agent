/**
 * 处理 draw 命令 - 发送绘图指令到本地 AutoCAD 引擎
 */

import { CommandHandlerContext, CommandEvent } from './types';

export function handleDrawCommand(
  event: CommandEvent,
  ctx: CommandHandlerContext
): void {
  const { botMessageId, setMessages, localEngineUrl } = ctx;
  
  // 先更新消息
  setMessages((prev) => prev.map(msg => 
    msg.id === botMessageId 
      ? { ...msg, content: msg.content + '\n\n🚀 已发送绘图指令到 AutoCAD...' }
      : msg
  ));
  
  // 副作用：发送绘图请求
  const drawingData = event.data;
  fetch(`${localEngineUrl}/execute_drawing`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ drawing_data: drawingData })
  })
  .then(res => {
    if (!res.ok) throw new Error('Local engine error');
    return res.json();
  })
  .then(data => {
    console.log("Drawing executed locally:", data);
  })
  .catch(err => {
    console.error("Failed to execute drawing locally:", err);
    setMessages(current => current.map(m => 
      m.id === botMessageId 
        ? { ...m, content: m.content + '\n\n⚠️ 本地绘图引擎连接失败，请确保已启动。' }
        : m
    ));
  });
}

