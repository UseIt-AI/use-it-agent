# Community Workflows API Specification

> ⚠️ **Status: Draft / To Be Redesigned**
> 
> This document describes the planned API for Community Workflows feature.
> The implementation is minimal and will undergo significant changes in future iterations.

---

## Overview

Community Workflows allows users to:
1. Browse public workflows shared by other users
2. Fork (copy) community workflows to their own collection
3. Share their own workflows with the community

---

## Current Implementation (Minimal)

### Database

Uses existing `workflows` table with `is_public` flag:

```sql
-- workflows table (existing)
create table public.workflows (
  id uuid default uuid_generate_v4() primary key,
  owner_id uuid references auth.users(id) not null,
  name text not null,
  description text,
  version text default '1.0.0',
  definition jsonb not null default '{}'::jsonb,
  is_public boolean default false,  -- ← Controls visibility
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- RLS Policy for public workflows
create policy "Users can view public workflows" 
  on public.workflows for select 
  using (is_public = true);
```

### Current API (Supabase Direct)

#### List Public Workflows

```typescript
const { data, error } = await supabase
  .from('workflows')
  .select('id, name, description, updated_at, is_public')
  .eq('is_public', true)
  .order('updated_at', { ascending: false });
```

#### Fork a Public Workflow

```typescript
// 1. Fetch the original
const { data: original } = await supabase
  .from('workflows')
  .select('*')
  .eq('id', publicWorkflowId)
  .single();

// 2. Create a copy under current user
const { data: forked } = await supabase
  .from('workflows')
  .insert({
    name: `${original.name} (Fork)`,
    description: original.description,
    definition: original.definition,
    owner_id: currentUserId,
    is_public: false,  // Forked copy is private by default
  })
  .select()
  .single();
```

---

## Planned Features (Future)

### 1. Enhanced Data Model

```sql
-- New: workflow_metadata table
create table public.workflow_metadata (
  workflow_id uuid references public.workflows(id) on delete cascade primary key,
  
  -- Discovery
  tags text[] default '{}',
  category text,  -- 'automation', 'analysis', 'report', etc.
  
  -- Social
  fork_count int default 0,
  view_count int default 0,
  like_count int default 0,
  
  -- Author info (denormalized for performance)
  author_name text,
  author_avatar text,
  
  -- Moderation
  featured boolean default false,
  verified boolean default false,
  
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- New: workflow_likes table
create table public.workflow_likes (
  user_id uuid references auth.users(id) on delete cascade,
  workflow_id uuid references public.workflows(id) on delete cascade,
  created_at timestamptz default now(),
  primary key (user_id, workflow_id)
);

-- New: workflow_comments table (optional)
create table public.workflow_comments (
  id uuid default uuid_generate_v4() primary key,
  workflow_id uuid references public.workflows(id) on delete cascade,
  user_id uuid references auth.users(id) on delete cascade,
  content text not null,
  created_at timestamptz default now()
);
```

### 2. Planned API Endpoints

#### Discovery

```
GET /api/v1/community/workflows
Query Parameters:
  - category: string (filter by category)
  - tags: string[] (filter by tags)
  - sort: 'popular' | 'recent' | 'trending'
  - search: string (full-text search)
  - page: number
  - limit: number

Response:
{
  workflows: CommunityWorkflow[],
  total: number,
  page: number,
  hasMore: boolean
}
```

#### Workflow Details

```
GET /api/v1/community/workflows/{id}

Response:
{
  workflow: CommunityWorkflow,
  author: UserProfile,
  stats: {
    forks: number,
    views: number,
    likes: number
  },
  userInteraction: {
    liked: boolean,
    forked: boolean
  }
}
```

#### Social Actions

```
POST /api/v1/community/workflows/{id}/like
DELETE /api/v1/community/workflows/{id}/like

POST /api/v1/community/workflows/{id}/fork
Response: { workflow: Workflow }  // The forked copy
```

#### Publishing

```
POST /api/v1/community/workflows/{id}/publish
Request:
{
  tags: string[],
  category: string,
  description: string
}

DELETE /api/v1/community/workflows/{id}/publish
// Unpublish (set is_public = false)
```

### 3. Planned Types

```typescript
interface CommunityWorkflow extends WorkflowListItem {
  author: {
    id: string;
    name: string;
    avatar?: string;
  };
  stats: {
    forks: number;
    views: number;
    likes: number;
  };
  tags: string[];
  category: string;
  featured: boolean;
  verified: boolean;
}

interface CommunityFilters {
  category?: string;
  tags?: string[];
  sort?: 'popular' | 'recent' | 'trending';
  search?: string;
}

interface CommunityPagination {
  page: number;
  limit: number;
}
```

### 4. UI Enhancements (Planned)

```
┌─────────────────────────────────────────────────────────────────────┐
│  COMMUNITY                                                    [🔍]  │
├─────────────────────────────────────────────────────────────────────┤
│  [All] [Automation] [Analysis] [Reports] [Templates]               │
├─────────────────────────────────────────────────────────────────────┤
│  ⭐ Featured                                                        │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  📁 Channel Analysis Workflow          ⬇️ 234  ❤️ 89        │   │
│  │     by @username • automation                               │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  📊 Popular This Week                                               │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  📁 Report Generator                   ⬇️ 156  ❤️ 45        │   │
│  │     by @another • report                                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Migration Path

1. **Phase 1 (Current)**: Basic is_public flag, simple fork
2. **Phase 2**: Add metadata table, tags, categories
3. **Phase 3**: Add social features (likes, comments)
4. **Phase 4**: Add discovery features (search, trending)
5. **Phase 5**: Add moderation (featured, verified)

---

## Notes

- Consider rate limiting for fork operations
- Need to handle workflow versioning for forked copies
- Consider notification system for workflow updates
- May need content moderation for public workflows


