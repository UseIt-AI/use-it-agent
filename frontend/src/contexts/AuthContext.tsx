import { createContext, useContext, ReactNode } from 'react'
import { useStore } from '@/contexts/RootStoreContext'
import type { AuthStore } from '@/stores/authStore'

const AuthContext = createContext<AuthStore | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const { authStore } = useStore()
  return <AuthContext.Provider value={authStore}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
