/**
 * 处理 execute_excel_text 命令 - 发送 Excel 文本执行请求到本地引擎
 */

import { CommandHandlerContext, CommandEvent } from './types';

export function handleExcelExecutorCommand(
  event: CommandEvent,
  ctx: CommandHandlerContext
): void {
  const { botMessageId, setMessages, localEngineUrl } = ctx;

  const executorData = event.data;

  // 先更新消息
  setMessages(current => current.map(m =>
    m.id === botMessageId
      ? { ...m, content: m.content + '\n\n📝 正在启动 Excel 文本执行器...' }
      : m
  ));

  // 异步处理流式响应
  const processStream = async () => {
    try {
      const response = await fetch(`${localEngineUrl}/execute_excel_text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(executorData)
      });

      if (!response.ok) throw new Error('Local engine error');

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No reader available");

      const decoder = new TextDecoder();
      let execBuffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        execBuffer += decoder.decode(value, { stream: true });
        const execLines = execBuffer.split('\n');
        execBuffer = execLines.pop() || '';

        for (const execLine of execLines) {
          if (!execLine.trim()) continue;
          try {
            const execEvent = JSON.parse(execLine);

            setMessages(current => current.map(m => {
              if (m.id !== botMessageId) return m;

              let newContent = m.content;

              // 处理不同类型的事件
              if (execEvent.type === 'status') {
                // 简单去重
                if (!newContent.includes(execEvent.content)) {
                  newContent += `\n> ${execEvent.content}`;
                }
              } else if (execEvent.type === 'error') {
                newContent += `\n\n❌ **错误**: ${execEvent.content}`;
              } else if (execEvent.type === 'finished') {
                if (execEvent.content.success) {
                  newContent += `\n\n✅ **执行完成！**`;
                  newContent += `\n📄 代码文件: ${execEvent.content.code_file}`;
                  if (execEvent.content.output) {
                    newContent += `\n\n**输出:**\n\`\`\`\n${execEvent.content.output}\n\`\`\``;
                  }
                }
              }

              return { ...m, content: newContent };
            }));

          } catch (e) {
            console.error("Error parsing executor stream", e);
          }
        }
      }
    } catch (err) {
      console.error("Failed to execute Excel text processor locally:", err);
      setMessages(current => current.map(m =>
        m.id === botMessageId
          ? { ...m, content: m.content + '\n\n⚠️ 本地 Excel 执行器连接失败，请确保已启动。' }
          : m
      ));
    }
  };

  // 启动异步流程
  processStream();
}
