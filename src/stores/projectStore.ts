import { makeAutoObservable, runInAction } from "mobx"
import { Project } from "@/types/project"
import { useWorkspaceStore } from "@/stores/useWorkspaceStore"
import type { RootStore } from "./rootStore"
import { Notification } from "@douyinfe/semi-ui"

class ProjectStore {
  rootStore: RootStore

  currentProject: Project | null = null
  recentProjects: Project[] = []
  isLoading = true
  isSwitching = false

  constructor(rootStore: RootStore) {
    this.rootStore = rootStore

    makeAutoObservable(this, {
      rootStore: false
    } as any)

  }

  async initialize() {
    runInAction(() => {
      this.isLoading = true
      this.currentProject = null
      this.recentProjects = []
    })

    try {
      const projects = await this.refreshRecentProjects()

      if (projects.length > 0) {
        await this.openProject(projects[0].id)
      }
    } catch (e) {
      console.error(e)
      runInAction(() => {
        this.recentProjects = []
      })
    } finally {
      runInAction(() => {
        this.isLoading = false
      })
    }
  }

  reset() {
    this.currentProject = null
    this.recentProjects = []
    this.isLoading = false
    this.isSwitching = false

    useWorkspaceStore.getState().resetForProjectSwitch()
  }

  refreshRecentProjects = async (): Promise<Project[]> => {
    try {
      let localProjects = await window.electron.getRecentProjects()

      localProjects.sort((a, b) => b.lastModified - a.lastModified)

      runInAction(() => { this.recentProjects = localProjects })
      return localProjects
    } catch (error) {
      console.error('Failed to refresh recent projects:', error)
      return []
    }
  }

  getNextSequentialDefaultProjectName = async (): Promise<string> => {
    return computeNextDefaultProjectName([])
  }

  createProject = async (name: string): Promise<Project | null> => {
    try {
      const { projectId } = await window.electron.createProject(name)
      return await this.openProject(projectId)
    } catch (error) {
      console.error('Failed to create project:', error)
      Notification.warning({title:error})
    }
  }

  openProject = async (projectId: string): Promise<Project | null> => {
    runInAction(() => this.isSwitching = true);
    try {
      const project = await window.electron.openProject(projectId)
      useWorkspaceStore.getState().resetForProjectSwitch()
      runInAction(() => { this.currentProject = project })
      await this.refreshRecentProjects()
      return project
    } catch (error) {
      console.error('Failed to open project:', error)
      return null
    } finally {
      runInAction(() => this.isSwitching = false);
    }
  }

  importProject = async (): Promise<boolean> => {
    if (!window.electron?.importProjectFolder) return false
    try {
      const project = await window.electron.importProjectFolder()
      if (project) {
        useWorkspaceStore.getState().resetForProjectSwitch()
        runInAction(() => { this.currentProject = project })
        await this.refreshRecentProjects()
        return true
      }
    } catch (error) {
      console.error('Failed to import project:', error)
    }
    return false
  }

  deleteProject = async (projectId: string): Promise<boolean> => {
    try {
      await window.electron.deleteProject(projectId)
      await this.refreshRecentProjects()
      return true
    } catch (error) {
      console.error('Failed to delete project:', error)
      return false
    }
  }

  closeProject = (): void => {
    this.currentProject = null
    if (window.electron?.setAppConfig) {
      window.electron.setAppConfig({ lastOpenedProjectId: null })
    }
  }
}

export default ProjectStore

const DEFAULT_PROJECT_BASE = 'New Project'

function computeNextDefaultProjectName(existingNames: string[]): string {
  let max = 0
  const escaped = DEFAULT_PROJECT_BASE.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const numbered = new RegExp(`^${escaped} (\\d+)$`)
  for (const raw of existingNames) {
    const name = typeof raw === 'string' ? raw.trim() : ''
    if (!name) continue
    if (name === DEFAULT_PROJECT_BASE) {
      max = Math.max(max, 1)
      continue
    }
    const m = numbered.exec(name)
    if (m) {
      const n = parseInt(m[1], 10)
      if (!Number.isNaN(n)) max = Math.max(max, n)
    }
  }
  return `${DEFAULT_PROJECT_BASE} ${max + 1}`
}
