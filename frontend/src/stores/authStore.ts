import { makeAutoObservable, runInAction } from 'mobx'
import type { RootStore } from './rootStore'
import { LOCAL_OFFLINE_USER_ID } from '@/services/localOfflineStore'

/** 与 UI 兼容的最小用户模型（无 Supabase） */
export interface LocalUser {
  id: string
  email?: string
  app_metadata?: Record<string, unknown>
  user_metadata?: Record<string, unknown>
}

export interface LocalSession {
  access_token: string
  refresh_token: string
  user: LocalUser
}

export interface Profile {
  id: string
  username: string | null
  email: string | null
  avatar_url: string | null
  subscription_tier: string | null
  subscription_status: string | null
  credits_balance: number
  last_daily_login_bonus_at: string | null
  current_period_end: string | null
}

function defaultProfile(userId: string): Profile {
  return {
    id: userId,
    username: 'Local',
    email: 'local@offline',
    avatar_url: null,
    subscription_tier: 'local',
    subscription_status: 'active',
    credits_balance: 0,
    last_daily_login_bonus_at: null,
    current_period_end: null,
  }
}

function defaultSession(): LocalSession {
  const user: LocalUser = {
    id: LOCAL_OFFLINE_USER_ID,
    email: 'local@offline',
    user_metadata: { name: 'Local User' },
  }
  return {
    access_token: 'offline-local',
    refresh_token: 'offline-local',
    user,
  }
}

export class AuthStore {
  rootStore: RootStore
  session: LocalSession | null = defaultSession()
  user: LocalUser | null = defaultSession().user
  profile: Profile | null = defaultProfile(LOCAL_OFFLINE_USER_ID)
  loading = false

  constructor(rootStore: RootStore) {
    this.rootStore = rootStore
    makeAutoObservable(this, {
      rootStore: false,
    } as any)
    runInAction(() => {
      this.loading = false
    })
  }

  signInWithEmail = async (_email: string, _password: string): Promise<void> => {
    runInAction(() => {
      this.session = defaultSession()
      this.user = this.session.user
      this.profile = defaultProfile(LOCAL_OFFLINE_USER_ID)
    })
  }

  signInWithGoogle = async (): Promise<void> => {
    throw new Error('离线发行版不支持 Google 登录')
  }

  signOut = async (): Promise<void> => {
    runInAction(() => {
      this.session = null
      this.user = null
      this.profile = null
    })
  }

  refreshProfile = async (): Promise<void> => {
    if (!this.user?.id) return
    runInAction(() => {
      this.profile = defaultProfile(this.user!.id)
    })
  }

  updateProfile = async (updates: { username?: string | null; avatar_url?: string | null }): Promise<void> => {
    if (!this.user?.id) throw new Error('Not authenticated')
    runInAction(() => {
      this.profile = {
        ...(this.profile ?? defaultProfile(this.user!.id)),
        username: updates.username ?? this.profile?.username ?? null,
        avatar_url: updates.avatar_url ?? this.profile?.avatar_url ?? null,
      }
    })
  }
}

export default AuthStore
