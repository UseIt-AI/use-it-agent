import { useEffect, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';

export function useSkillsRootPath() {
  const { user } = useAuth();
  const [rootPath, setRootPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        if (!window.electron?.fsGetSkillsRoot) {
          throw new Error('Skills API not available');
        }
        const path = await window.electron.fsGetSkillsRoot(user?.id);
        if (active) setRootPath(path);
      } catch (err: any) {
        if (active) {
          setError(err?.message || 'Failed to resolve skills path');
          setRootPath(null);
        }
      } finally {
        if (active) setLoading(false);
      }
    };

    load();

    return () => {
      active = false;
    };
  }, [user?.id]);

  return { rootPath, loading, error };
}
