/** 等待指定毫秒数，例如 await sleep(1000) 等待 1 秒 */
export const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

/** 将日期字符串格式化为英文可读形式，例如 "Apr 6, 2026, 10:30 AM" */
export const formatDisplayDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

/** 将时间戳格式化为相对时间，例如 "Today"、"Yesterday"、"3d ago" 或本地日期 */
export const formatRelativeTime = (timestamp: number, { showTime = false, showDate = false }: { showTime?: boolean; showDate?: boolean } = {}): string => {
  const date = new Date(timestamp);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

  const timeStr = `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
  const dateStr = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${timeStr}`;

  if (showDate && diffDays >= 2) return dateStr;

  if (diffDays === 0) return showTime ? `Today ${timeStr}` : 'Today';
  if (diffDays === 1) return showTime ? `Yesterday ${timeStr}` : 'Yesterday';
  if (diffDays < 7) return showTime ? `${diffDays}d ago ${timeStr}` : `${diffDays}d ago`;
  return showTime ? `${date.toLocaleDateString()} ${timeStr}` : date.toLocaleDateString();
};

export const formatDate = (dateStr: string, format = 'YYYY-MM-DD HH:mm') => {
  const d = new Date(dateStr);
  const map: Record<string, string> = {
    YYYY: String(d.getFullYear()),
    MM: String(d.getMonth() + 1).padStart(2, '0'),
    DD: String(d.getDate()).padStart(2, '0'),
    HH: String(d.getHours()).padStart(2, '0'),
    mm: String(d.getMinutes()).padStart(2, '0'),
    ss: String(d.getSeconds()).padStart(2, '0'),
  };
  return format.replace(/YYYY|MM|DD|HH|mm|ss/g, token => map[token]);
};

