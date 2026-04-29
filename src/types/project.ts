export interface Project {
  id: string;
  name: string;
  path: string;
  created_at?: number;
  lastModified: number;
  exists?: boolean; // 本地是否存在
  isCloudOnly?: boolean; // 是否仅在云端存在
}

export interface ProjectConfig {
  id: string;
  name: string;
  createdAt: number;
  version: string;
  description?: string;
}

