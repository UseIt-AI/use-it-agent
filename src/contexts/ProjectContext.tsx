import React, { createContext, useContext } from 'react'
import { Project } from '../types/project'
import { useStore } from '@/contexts/RootStoreContext'

interface ProjectContextType {
  currentProject: Project | null
  recentProjects: Project[]
  isLoading: boolean
  isSwitching: boolean
  createProject: (name: string) => Promise<Project | null>
  getNextSequentialDefaultProjectName: () => Promise<string>
  openProject: (projectId: string) => Promise<Project | null>
  importProject: () => Promise<boolean>
  deleteProject: (projectId: string) => Promise<boolean>
  refreshRecentProjects: () => Promise<Project[]>
  closeProject: () => void
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined)

export function useProject() {
  const context = useContext(ProjectContext)
  if (context === undefined) {
    throw new Error('useProject must be used within a ProjectProvider')
  }
  return context
}

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const { projectStore } = useStore()
  return (
    <ProjectContext.Provider value={projectStore}>
      {children}
    </ProjectContext.Provider>
  )
}
