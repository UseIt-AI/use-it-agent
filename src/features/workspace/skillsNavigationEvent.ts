/**
 * Skills Navigation Event
 * 
 * 用于在点击 skill chip 时通知切换到 Skills 页面并展开对应文件夹
 */

export type SkillsNavigationPayload = {
  /** Skill 名称（文件夹名） */
  skillName: string;
  /** S3 key（可选，用于验证） */
  s3Key?: string;
};

type SkillsNavigationListener = (payload: SkillsNavigationPayload) => void;

const listeners = new Set<SkillsNavigationListener>();

/**
 * 订阅 skills 导航事件
 */
export function subscribeSkillsNavigation(listener: SkillsNavigationListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * 触发 skills 导航事件
 */
export function emitSkillsNavigation(payload: SkillsNavigationPayload): void {
  listeners.forEach((listener) => {
    try {
      listener(payload);
    } catch (err) {
      console.error('[SkillsNavigation] Listener error:', err);
    }
  });
}
