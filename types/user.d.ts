
interface Profile {
  id: string
  username: string | null
  email: string | null
  avatar_url: string | null
  subscription_tier: 'free' | 'pro' | 'enterprise' | string | null
  subscription_status: string | null
  // PostgREST may return numeric as string depending on configuration
  credits_balance: number | string | null
  last_daily_login_bonus_at?: string | null
  current_period_end?: string | null
}