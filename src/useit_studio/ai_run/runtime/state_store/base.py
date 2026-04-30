"""
State Store Base Interface

Abstract base class defining the interface for state storage backends.
All storage implementations (Memory, Redis, etc.) must implement this interface.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from contextlib import contextmanager


class StateStore(ABC):
    """
    Abstract base class for state storage backends.
    
    Provides a unified interface for storing and retrieving agent runtime state,
    supporting both development (memory) and production (Redis) environments.
    
    Key responsibilities:
    - Store/retrieve RuntimeStateManager state
    - Store/retrieve session progress
    - Manage task lifecycle (heartbeat, cleanup)
    - Provide distributed locking for concurrent access
    """
    
    # ==================== Runtime State Operations ====================
    
    @abstractmethod
    def save_runtime_state(self, task_id: str, state_data: Dict[str, Any]) -> bool:
        """
        Save RuntimeStateManager's complete state.
        
        Args:
            task_id: Unique task identifier
            state_data: Serialized state from RuntimeStateManager.to_dict()
            
        Returns:
            True if save successful, False otherwise
        """
        pass
    
    @abstractmethod
    def load_runtime_state(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Load RuntimeStateManager's complete state.
        
        Args:
            task_id: Unique task identifier
            
        Returns:
            State dictionary if exists, None otherwise
        """
        pass
    
    @abstractmethod
    def exists_runtime_state(self, task_id: str) -> bool:
        """
        Check if runtime state exists for a task.
        
        Args:
            task_id: Unique task identifier
            
        Returns:
            True if state exists, False otherwise
        """
        pass
    
    # ==================== Session Progress Operations ====================
    
    @abstractmethod
    def save_session_progress(self, task_id: str, progress: Dict[str, Any]) -> bool:
        """
        Save session progress data.
        
        Args:
            task_id: Unique task identifier
            progress: Session progress dictionary
            
        Returns:
            True if save successful, False otherwise
        """
        pass
    
    @abstractmethod
    def load_session_progress(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Load session progress data.
        
        Args:
            task_id: Unique task identifier
            
        Returns:
            Progress dictionary if exists, None otherwise
        """
        pass
    
    # ==================== Task Lifecycle Operations ====================
    
    @abstractmethod
    def delete_task_state(self, task_id: str) -> bool:
        """
        Delete all state data for a task.
        
        Removes runtime state, session progress, heartbeat, and any locks.
        
        Args:
            task_id: Unique task identifier
            
        Returns:
            True if deletion successful, False otherwise
        """
        pass
    
    @abstractmethod
    def list_active_tasks(self) -> List[str]:
        """
        List all active task IDs.
        
        Returns:
            List of task IDs with active state
        """
        pass
    
    @abstractmethod
    def heartbeat(self, task_id: str, ttl_seconds: int = 300) -> bool:
        """
        Update task heartbeat timestamp.
        
        Used to detect zombie tasks (tasks that stopped without cleanup).
        
        Args:
            task_id: Unique task identifier
            ttl_seconds: Time-to-live for heartbeat (default 5 minutes)
            
        Returns:
            True if heartbeat updated, False otherwise
        """
        pass
    
    @abstractmethod
    def is_task_alive(self, task_id: str) -> bool:
        """
        Check if task is still alive (has recent heartbeat).
        
        Args:
            task_id: Unique task identifier
            
        Returns:
            True if task has valid heartbeat, False otherwise
        """
        pass
    
    @abstractmethod
    def get_stale_tasks(self, max_age_seconds: int = 600) -> List[str]:
        """
        Get list of tasks with stale heartbeats.
        
        Args:
            max_age_seconds: Maximum age for heartbeat to be considered valid
            
        Returns:
            List of task IDs with stale heartbeats
        """
        pass
    
    # ==================== Distributed Locking ====================
    
    @abstractmethod
    def acquire_lock(self, task_id: str, timeout_seconds: int = 30) -> bool:
        """
        Acquire exclusive lock for a task.
        
        Prevents concurrent modifications to the same task state.
        
        Args:
            task_id: Unique task identifier
            timeout_seconds: Lock timeout (auto-release if holder crashes)
            
        Returns:
            True if lock acquired, False if already locked
        """
        pass
    
    @abstractmethod
    def release_lock(self, task_id: str) -> bool:
        """
        Release exclusive lock for a task.
        
        Args:
            task_id: Unique task identifier
            
        Returns:
            True if lock released, False if not held
        """
        pass
    
    @abstractmethod
    def is_locked(self, task_id: str) -> bool:
        """
        Check if task is currently locked.
        
        Args:
            task_id: Unique task identifier
            
        Returns:
            True if locked, False otherwise
        """
        pass
    
    @contextmanager
    def lock(self, task_id: str, timeout_seconds: int = 30):
        """
        Context manager for task locking.
        
        Usage:
            with store.lock(task_id):
                # Exclusive access to task state
                state = store.load_runtime_state(task_id)
                # ... modify state ...
                store.save_runtime_state(task_id, state)
        
        Args:
            task_id: Unique task identifier
            timeout_seconds: Lock timeout
            
        Raises:
            RuntimeError: If lock cannot be acquired
        """
        if not self.acquire_lock(task_id, timeout_seconds):
            raise RuntimeError(f"Failed to acquire lock for task {task_id}")
        try:
            yield
        finally:
            self.release_lock(task_id)
    
    # ==================== Utility Methods ====================
    
    @abstractmethod
    def clear_all(self) -> bool:
        """
        Clear all stored state (use with caution!).
        
        Primarily for testing and development.
        
        Returns:
            True if cleared successfully
        """
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.
        
        Returns:
            Dictionary with stats like total_tasks, memory_usage, etc.
        """
        pass
    
    def close(self):
        """
        Close any connections and cleanup resources.
        
        Override in subclasses that need cleanup.
        """
        pass
