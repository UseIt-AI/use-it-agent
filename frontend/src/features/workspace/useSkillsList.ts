import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';

type SkillEntry = {
  name: string;
  type: 'file' | 'folder';
};

export interface SkillInfo {
  /** Skill 文件夹名称 */
  name: string;
  /** S3 key 格式: skills/{user_id}/{skill_name} */
  s3Key: string;
}

export function useSkillsList(rootPath?: string | null) {
  const { user } = useAuth();
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const watcherCleanupRef = useRef<(() => void) | null>(null);

  const loadSkills = useCallback(async () => {
    if (!rootPath || !user?.id) {
      setSkills([]);
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const electron = window.electron as any;
      if (!electron?.fsReadDirectory) {
        throw new Error('File system API not available');
      }
      const children: SkillEntry[] = await electron.fsReadDirectory(rootPath);
      const skillInfos: SkillInfo[] = children
        .filter((child) => child.type === 'folder')
        .map((child) => child.name)
        .filter(Boolean)
        .sort((a, b) => a.localeCompare(b))
        .map((name) => ({
          name,
          s3Key: `skills/${user.id}/${name}`,
        }));
      setSkills(skillInfos);
    } catch (err: any) {
      setError(err?.message || 'Failed to load skills');
      setSkills([]);
    } finally {
      setLoading(false);
    }
  }, [rootPath, user?.id]);

  useEffect(() => {
    let isMounted = true;
    const electron = window.electron as any;

    const initialize = async () => {
      if (!rootPath) {
        setSkills([]);
        return;
      }
      await loadSkills();

      if (electron?.fsWatchDirectory && electron?.onFsDirectoryChanged) {
        try {
          await electron.fsWatchDirectory(rootPath);
          const cleanup = electron.onFsDirectoryChanged((changeData: any) => {
            if (!isMounted) return;
            if (debounceTimerRef.current) {
              clearTimeout(debounceTimerRef.current);
            }
            debounceTimerRef.current = setTimeout(() => {
              if (isMounted) loadSkills();
            }, 300);
          });
          watcherCleanupRef.current = cleanup || null;
        } catch (err) {
          console.error('Failed to watch skills directory:', err);
        }
      }
    };

    initialize();

    return () => {
      isMounted = false;
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
      if (watcherCleanupRef.current) {
        watcherCleanupRef.current();
        watcherCleanupRef.current = null;
      }
      if (rootPath && electron?.fsUnwatchDirectory) {
        electron.fsUnwatchDirectory(rootPath).catch(console.error);
      }
    };
  }, [rootPath, loadSkills]);

  /** 便捷方法：只返回 skill 名称列表（用于向后兼容） */
  const skillNames = skills.map((s) => s.name);

  /** 便捷方法：只返回 S3 key 列表 */
  const skillS3Keys = skills.map((s) => s.s3Key);

  /** 根据 S3 key 获取 skill 名称 */
  const getSkillNameByS3Key = useCallback((s3Key: string): string | undefined => {
    const skill = skills.find((s) => s.s3Key === s3Key);
    return skill?.name;
  }, [skills]);

  /** 根据 skill 名称获取 S3 key */
  const getS3KeyBySkillName = useCallback((name: string): string | undefined => {
    const skill = skills.find((s) => s.name === name);
    return skill?.s3Key;
  }, [skills]);

  return {
    /** 完整的 skill 信息列表 */
    skills,
    /** 只返回 skill 名称列表（向后兼容） */
    skillNames,
    /** 只返回 S3 key 列表 */
    skillS3Keys,
    /** 根据 S3 key 获取 skill 名称 */
    getSkillNameByS3Key,
    /** 根据 skill 名称获取 S3 key */
    getS3KeyBySkillName,
    loading,
    error,
    refresh: loadSkills,
  };
}
