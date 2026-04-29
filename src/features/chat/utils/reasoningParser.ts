/**
 * Reasoning Parser - 解析 CUA 思考过程的工具模块
 * 
 * 支持两种格式：
 * 1. 新格式：<thinking>...</thinking> 标签包裹的纯文本
 * 2. 旧格式：JSON 格式 {"Observation": "...", "Reasoning": "...", ...}
 */

type ReasoningFormat = 'thinking-tag' | 'json' | 'plain';

/**
 * 检测 reasoning 内容的格式类型
 */
function detectReasoningFormat(raw: string): ReasoningFormat {
  const trimmed = raw.trim();
  
  // 检测 <thinking> 标签
  if (trimmed.includes('<thinking>') || trimmed.startsWith('<thinking')) {
    return 'thinking-tag';
  }
  
  // 检测 JSON 格式（以 { 开头）
  if (trimmed.startsWith('{')) {
    return 'json';
  }
  
  // 其他情况视为纯文本
  return 'plain';
}

/**
 * 提取 <thinking>...</thinking> 标签内的内容
 * 支持流式传输（</thinking> 可能还未到达）
 * 
 * 关键：即使内容很少（如刚收到 <thinking>\n），也要返回已有内容，
 * 而不是返回空字符串，否则流式效果无法体现。
 */
function extractThinkingContent(raw: string): string {
  // 查找 <thinking> 标签的位置
  const startTag = '<thinking>';
  const endTag = '</thinking>';
  
  const startIndex = raw.indexOf(startTag);
  if (startIndex === -1) {
    return '';
  }
  
  // 提取 <thinking> 之后的内容
  const contentStart = startIndex + startTag.length;
  const endIndex = raw.indexOf(endTag, contentStart);
  
  // 如果找到了 </thinking>，取中间内容；否则取到字符串末尾
  let content = endIndex !== -1 
    ? raw.substring(contentStart, endIndex) 
    : raw.substring(contentStart);
  
  // 过滤掉 JSON 代码块（```json...```），这是给后端的结构化输出
  content = content.replace(/```json[\s\S]*?```/g, '');
  // 也过滤掉未闭合的 JSON 代码块（流式传输中）
  content = content.replace(/```json[\s\S]*$/g, '');
  
  // 注意：这里不再 trim()，保留换行符以保持流式输出的自然感
  // 只去除开头的空白（因为 <thinking> 后通常有一个换行）
  content = content.replace(/^\s*\n/, '');
  
  return content;
}

/**
 * 从 JSON 格式的字符串中提取指定字段的值并拼接成段落
 * （保持原有逻辑，支持旧格式）
 */
function extractJsonFields(raw: string): string {
  // 定义需要提取的字段及其顺序
  const targetKeys = ['Observation', 'Reasoning', 'Action', 'Expectation'];
  
  const values: string[] = [];
  
  for (const key of targetKeys) {
    // 构造正则：匹配 "Key": "Value" 结构
    // 1. \"${key}\"\s*:\s*\" -> 匹配 "Key": "
    // 2. ((?:[^"\\]|\\.)*) -> 捕获 Value，允许非引号字符或转义字符
    // 3. 向前断言，遇到引号、右大括号或字符串结尾停止（支持流式截断）
    const regex = new RegExp(`"${key}"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)`, 's');
    const match = raw.match(regex);
    
    if (match && match[1]) {
      // 处理 JSON 转义字符 (如 \n, \", \\)
      let cleanValue = match[1]
        .replace(/\\n/g, '\n')
        .replace(/\\"/g, '"')
        .replace(/\\\\/g, '\\');
        
      if (cleanValue.trim()) {
        values.push(cleanValue.trim());
      }
    }
  }
  
  // 如果提取到了内容，用双换行拼接（形成段落）
  if (values.length > 0) {
    return values.join('\n\n');
  }
  
  return '';
}

/**
 * 解析 Reasoning 内容（主入口函数）
 * 
 * @param raw - 原始 reasoning 字符串（可能是流式累积的）
 * @returns 解析后的人类可读文本
 */
export function parseReasoning(raw: string): string {
  if (!raw) return '';
  
  const format = detectReasoningFormat(raw);
  
  switch (format) {
    case 'thinking-tag':
      return extractThinkingContent(raw);
    
    case 'json':
      return extractJsonFields(raw);
    
    case 'plain':
      // 纯文本直接返回
      return raw.trim();
    
    default:
      return '';
  }
}
