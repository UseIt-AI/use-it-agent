import { app, BrowserWindow, dialog, ipcMain } from 'electron';
import { randomUUID } from 'node:crypto';
import * as fs from 'fs';
import path from 'node:path';
import { loadConfig, saveConfig } from './appConfigIpcHandle';

const documentsPath = app.getPath('documents');
const baseDir = path.join(documentsPath, 'UseItAgent', 'Projects');

class ProjectIpcHandle {

  init() {
      // 创建新项目
      ipcMain.handle('create-project', async (_event, { name }: { name: string; }) => {
        try {
          const projectId = randomUUID();
          
          // 使用纯项目名称作为文件夹名（不加 uuid 后缀）
          const projectDirName = name || 'Untitled Project';
          const projectPath = path.join(baseDir, projectDirName);
    
          // 检查是否已存在同名项目目录
          if (fs.existsSync(projectPath)) {
            return { success: false, error: `项目名称 "${name}" 已存在，请使用其他名称` };
          }
    
          // 创建项目目录
          fs.mkdirSync(projectPath, { recursive: true });
    
          // 创建子文件夹
          const subFolders = ['uploads', 'outputs', 'downloads', 'workspace'];
          subFolders.forEach(folder => {
            fs.mkdirSync(path.join(projectPath, folder), { recursive: true });
          });
    
          // 创建 project.json 元数据（在 .cua 文件夹下）
          const now = Date.now();
          const projectMeta = {
            id: projectId,
            name: name,
            createdAt: Date.now(),
            lastModified: now,
            version: '1.0'
          };
          const projectJsonPath = getProjectJsonPath(projectPath);
          fs.writeFileSync(projectJsonPath, JSON.stringify(projectMeta, null, 2));
    
          // 更新 app-config
          const config = loadConfig();
          const projects = config.projects || {};
          projects[projectId] = {
            ...projectMeta,
            path: projectPath
          };
          
          saveConfig({
            projects,
            lastOpenedProjectId: projectId
          });
    
          return { success: true, projectId, projectPath };
        } catch (error: any) {
          return { success: false, error: error.message };
        }
      });
    
      // 获取最近项目列表
      ipcMain.handle('get-recent-projects', async (_event) => {
        try {
          if (!fs.existsSync(baseDir)) {
            return { success: true, projects: [] };
          }
          const entries = fs.readdirSync(baseDir, { withFileTypes: true });
          const projectsList = entries
            .filter(e => e.isDirectory())
            .map(e => {
              const projectPath = path.join(baseDir, e.name);
              const metaPath = getProjectJsonPath(projectPath);
              try {
                if (fs.existsSync(metaPath)) {
                  const meta = JSON.parse(fs.readFileSync(metaPath, 'utf-8'));
                  return { ...meta, path: projectPath, exists: true };
                }
              } catch (e) {
                console.warn(`[get-recent-projects] 读取 .cua/project.json 失败: ${projectPath}`, e);
                return null;
              }
            })
            .filter(Boolean)
            .sort((a: any, b: any) => b.lastModified - a.lastModified);
          console.log("baseDir=====>",projectsList);
          return { success: true, projects: projectsList };
        } catch (error: any) {
          return { success: false, error: error.message };
        }
      });
    
      // 打开项目 (设置当前项目)
      ipcMain.handle('open-project', async (_event, { projectId }: { projectId: string }) => {
        try {
          const entries = fs.readdirSync(baseDir, { withFileTypes: true });
          const allProjectMeta = entries
              .filter(e => e.isDirectory())
              .map(e => {
                const projectPath = path.join(baseDir, e.name);
                const metaPath = getProjectJsonPath(projectPath);
                try {
                  if (!fs.existsSync(metaPath)) {
                    return null;
                  }
                  let meta = JSON.parse(fs.readFileSync(metaPath, 'utf-8'));
                  meta.path = projectPath;
                  return meta
                } catch (e) {
                  console.warn(`[get-recent-projects] 读取 .cua/project.json 失败: ${metaPath}`, e);
                  return null;
                }
              })
              .filter(Boolean)

          const project = allProjectMeta.find(meta => {
            if(meta.id === projectId){
              // 找到则更新meta数据，返回数据
              updateLastModified(meta.path)
              return true
            }
            return false
          })
          if(!project){
            return { success: false, error: 'Project not found' };
          }
          
          return { success: true, project };
        } catch (error: any) {
          return { success: false, error: error.message };
        }
      });
    
      // 删除项目
      ipcMain.handle('delete-project', async (_event, { projectId }: {  projectId: string }) => {
        try {
          const entries = fs.readdirSync(baseDir, { withFileTypes: true });
          const allProjectMeta = entries
              .filter(e => e.isDirectory())
              .map(e => {
                const projectPath = path.join(baseDir, e.name);
                const metaPath = getProjectJsonPath(projectPath);
                try {
                  if (!fs.existsSync(metaPath)) {
                    return null;
                  }
                  let meta = JSON.parse(fs.readFileSync(metaPath, 'utf-8'));
                  meta.path = projectPath;
                  return meta
                } catch (e) {
                  console.warn(`[get-recent-projects] 读取 .cua/project.json 失败: ${metaPath}`, e);
                  return null;
                }
              })
              .filter(Boolean)

          const project = allProjectMeta.find(meta => meta.id === projectId)
          if(!project){
            return { success: false, error: 'Project not found' };
          }
    
          // 获取项目路径
          const projectPath = project.path;
          
          // 1. 删除本地项目文件夹（如果存在）
          if (projectPath && fs.existsSync(projectPath)) {
            try {
              console.log(`[DeleteProject] 正在删除本地项目文件夹: ${projectPath}`);
              fs.rmSync(projectPath, { recursive: true, force: true });
              console.log(`[DeleteProject] ✅ 本地项目文件夹已删除: ${projectPath}`);
            } catch (error: any) {
              console.error(`[DeleteProject] 删除本地项目文件夹失败: ${projectPath}`, error);
              // 不阻止删除流程，只记录错误（可能文件夹已被手动删除）
            }
          } else {
            console.log(`[DeleteProject] 项目路径不存在或已删除: ${projectPath}`);
          }

          return { success: true };
        } catch (error: any) {
          return { success: false, error: error.message };
        }
      });
      
      // 导入现有项目文件夹
      ipcMain.handle('import-project-folder', async () => {
        const win = BrowserWindow.getAllWindows()[0];
        try {
            const result = await dialog.showOpenDialog(win, {
                title: 'Open Project Folder',
                properties: ['openDirectory']
            });
    
            if (result.canceled || result.filePaths.length === 0) {
                return { success: false, canceled: true };
            }
    
            const projectPath = result.filePaths[0];
            // 检查是否包含 project.json（先检查新位置 .cua/project.json，再检查旧位置以兼容）
            const metaPath = getProjectJsonPath(projectPath);
            const oldMetaPath = path.join(projectPath, 'project.json'); // 兼容旧位置
            let projectId = randomUUID();
            let projectName = path.basename(projectPath);
    
            // 优先检查新位置
            if (fs.existsSync(metaPath)) {
                try {
                    const meta = JSON.parse(fs.readFileSync(metaPath, 'utf-8'));
                    if (meta.id) projectId = meta.id;
                    if (meta.name) projectName = meta.name;
                } catch (e) {
                    console.warn('Invalid project.json, creating new meta');
                }
            } else if (fs.existsSync(oldMetaPath)) {
                // 兼容旧位置：如果旧位置存在，读取并迁移到新位置
                try {
                    const meta = JSON.parse(fs.readFileSync(oldMetaPath, 'utf-8'));
                    if (meta.id) projectId = meta.id;
                    if (meta.name) projectName = meta.name;
                    // 迁移到新位置
                    fs.writeFileSync(metaPath, JSON.stringify(meta, null, 2));
                    console.log('Migrated project.json from root to .cua folder');
                } catch (e) {
                    console.warn('Invalid project.json at old location, creating new meta');
                }
            } else {
                 // 如果没有 project.json，初始化它
                 const projectMeta = {
                    id: projectId,
                    name: projectName,
                    createdAt: Date.now(),
                    version: '1.0'
                  };
                  fs.writeFileSync(metaPath, JSON.stringify(projectMeta, null, 2));
            }
    
            // 保存到配置
            const config = loadConfig();
            const projects = config.projects || {};
            const now = Date.now();
            projects[projectId] = {
                id: projectId,
                name: projectName,
                path: projectPath,
                created_at: now,
                lastModified: now
            };
    
            saveConfig({
                projects,
                lastOpenedProjectId: projectId
            });
    
            return { success: true, projectId, project: projects[projectId] };
    
        } catch (error: any) {
            return { success: false, error: error.message };
        }
      });

  }

}

const getProjectDirByUserId = (userId:string) => {
    const documentsPath = app.getPath('documents');
    const useitAgentDir = path.join(documentsPath, 'UseitAgent');
    const userDir = path.join(useitAgentDir, `useitid_${userId}`);
    const baseDir = path.join(userDir, 'projects');
    return baseDir
}

// 获取 project.json 的路径（在 .cua 文件夹下）
const getProjectJsonPath = (projectPath: string): string => {
  const cuaDir = path.join(projectPath, '.cua');
  // 确保 .cua 文件夹存在
  if (!fs.existsSync(cuaDir)) {
    fs.mkdirSync(cuaDir, { recursive: true });
  }
  return path.join(cuaDir, 'project.json');
};

const updateLastModified = (projectPath: string) => {
    const metaPath = getProjectJsonPath(projectPath);
    if (!fs.existsSync(metaPath)) {
      return null;
    }
    const meta = JSON.parse(fs.readFileSync(metaPath, 'utf-8'));
    const date = Date.now();
    meta.lastModified = date;
    fs.writeFileSync(metaPath, JSON.stringify(meta, null, 2));
    return date;
}

export default new ProjectIpcHandle();
