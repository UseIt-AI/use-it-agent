/**
 * 处理 calculate_excel 命令 - 发送 Excel 试算请求到本地引擎
 */

import { CommandHandlerContext, CommandEvent } from './types';

export function handleExcelCommand(
  event: CommandEvent,
  ctx: CommandHandlerContext
): void {
  const { botMessageId, setMessages, localEngineUrl } = ctx;
  
  const calcData = event.data;
  
  // 先更新消息
  setMessages(current => current.map(m => 
    m.id === botMessageId 
      ? { ...m, content: m.content + '\n\n📊 正在启动 Excel 试算流程...' }
      : m
  ));

  // 异步处理流式响应
  const processStream = async () => {
    try {
      const response = await fetch(`${localEngineUrl}/execute_calculation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(calcData)
      });

      if (!response.ok) throw new Error('Local engine error');
      
      const reader = response.body?.getReader();
      if (!reader) throw new Error("No reader available");

      const decoder = new TextDecoder();
      let calcBuffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        calcBuffer += decoder.decode(value, { stream: true });
        const calcLines = calcBuffer.split('\n');
        calcBuffer = calcLines.pop() || '';

        for (const calcLine of calcLines) {
          if (!calcLine.trim()) continue;
          try {
            const calcEvent = JSON.parse(calcLine);
            
            setMessages(current => current.map(m => {
              if (m.id !== botMessageId) return m;

              let newContent = m.content;
              
              // 处理不同类型的事件
              if (calcEvent.type === 'status') {
                // 简单去重
                if (!newContent.includes(calcEvent.content)) {
                  newContent += `\n> ${calcEvent.content}`;
                }
              } else if (calcEvent.type === 'convergence') {
                if (calcEvent.content.converged) {
                  newContent += `\n\n✅ **收敛成功！** (第 ${calcEvent.content.round} 轮)`;
                } else {
                  newContent += `\n⚠️ 第 ${calcEvent.content.round} 轮未收敛 (无效行数: ${calcEvent.content.invalid_rows})`;
                }
              } else if (calcEvent.type === 'error') {
                newContent += `\n\n❌ **错误**: ${calcEvent.content}`;
              } else if (calcEvent.type === 'finished') {
                if (calcEvent.content.success) {
                  newContent += `\n\n🏁 **试算流程结束**`;
                }
              }

              return { ...m, content: newContent };
            }));

          } catch (e) {
            console.error("Error parsing calc stream", e);
          }
        }
      }
    } catch (err) {
      console.error("Failed to execute calculation locally:", err);
      setMessages(current => current.map(m => 
        m.id === botMessageId 
          ? { ...m, content: m.content + '\n\n⚠️ 本地计算引擎连接失败，请确保已启动。' }
          : m
      ));
    }
  };
  
  // 启动异步流程
  processStream();
}

