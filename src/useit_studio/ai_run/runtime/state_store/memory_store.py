"""
Memory State Store

In-memory implementation of StateStore for development and debugging.
State is stored in Python dictionaries and lost on process restart.

Features:
- Fast access (no network overhead)
- Simple debugging (can inspect state directly)
- Automatic cleanup of old tasks
- Thread-safe operations

Limitations:
- Not suitable for production (no persistence)
- Cannot scale horizontally (state not shared)
- Lost on process restart
"""

import time
import threading
import logging
from typing import Dict, Any, Optional, List
from collections import OrderedDict

from .base import StateStore
from .serializer import StateSerializer

logger = logging.getLogger(__name__)


class MemoryStateStore(StateStore):
    """
    In-memory state storage implementation.
    
    Suitable for:
    - Local development
    - Debugging
    - Single-instance deployments
    - Testing
    
    Not suitable for:
    - Production with multiple instances
    - Elastic scaling
    - High availability requirements
    """
    
    def __init__(
        self,
        max_tasks: int = 1000,
        default_ttl_seconds: int = 86400,  # 24 hours
        cleanup_interval_seconds: int = 3600,  # 1 hour
    ):
        """
        Initialize memory store.
        
        Args:
            max_tasks: Maximum number of tasks to keep in memory
            default_ttl_seconds: Default TTL for state data
            cleanup_interval_seconds: Interval for cleanup thread
        """
        self.max_tasks = max_tasks
        self.default_ttl_seconds = default_ttl_seconds
        self.cleanup_interval_seconds = cleanup_interval_seconds
        
        # Storage dictionaries
        self._runtime_states: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._session_progress: Dict[str, Dict[str, Any]] = {}
        self._heartbeats: Dict[str, float] = {}
        self._locks: Dict[str, float] = {}  # task_id -> lock_expiry_time
        self._state_timestamps: Dict[str, float] = {}  # task_id -> last_update_time
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Serializer for consistent format
        self._serializer = StateSerializer()
        
        # Cleanup thread
        self._cleanup_thread: Optional[threading.Thread] = None
        self._stop_cleanup = threading.Event()
        
        # Start cleanup thread
        self._start_cleanup_thread()
        
        logger.info(
            f"MemoryStateStore initialized: max_tasks={max_tasks}, "
            f"ttl={default_ttl_seconds}s, cleanup_interval={cleanup_interval_seconds}s"
        )
    
    def _start_cleanup_thread(self):
        """Start background cleanup thread"""
        if self._cleanup_thread is not None:
            return
        
        def cleanup_loop():
            while not self._stop_cleanup.wait(self.cleanup_interval_seconds):
                self._cleanup_expired()
        
        self._cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        self._cleanup_thread.start()
    
    def _cleanup_expired(self):
        """Remove expired state data"""
        now = time.time()
        expired_tasks = []
        
        with self._lock:
            # Find expired tasks
            for task_id, timestamp in list(self._state_timestamps.items()):
                if now - timestamp > self.default_ttl_seconds:
                    expired_tasks.append(task_id)
            
            # Remove expired
            for task_id in expired_tasks:
                self._remove_task_internal(task_id)
            
            # Enforce max_tasks limit (LRU eviction)
            while len(self._runtime_states) > self.max_tasks:
                oldest_task_id = next(iter(self._runtime_states))
                self._remove_task_internal(oldest_task_id)
                logger.debug(f"Evicted oldest task due to max_tasks limit: {oldest_task_id}")
        
        if expired_tasks:
            logger.info(f"Cleaned up {len(expired_tasks)} expired tasks")
    
    def _remove_task_internal(self, task_id: str):
        """Internal method to remove task (must hold lock)"""
        self._runtime_states.pop(task_id, None)
        self._session_progress.pop(task_id, None)
        self._heartbeats.pop(task_id, None)
        self._locks.pop(task_id, None)
        self._state_timestamps.pop(task_id, None)
    
    # ==================== Runtime State Operations ====================
    
    def save_runtime_state(self, task_id: str, state_data: Dict[str, Any]) -> bool:
        """Save runtime state to memory"""
        try:
            with self._lock:
                # Serialize to ensure consistent format
                serialized = self._serializer.serialize(state_data)
                deserialized = self._serializer.deserialize(serialized)
                
                # Store (move to end for LRU)
                if task_id in self._runtime_states:
                    self._runtime_states.move_to_end(task_id)
                self._runtime_states[task_id] = deserialized
                self._state_timestamps[task_id] = time.time()
                
                logger.debug(f"Saved runtime state for task {task_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to save runtime state for {task_id}: {e}")
            return False
    
    def load_runtime_state(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Load runtime state from memory"""
        with self._lock:
            state = self._runtime_states.get(task_id)
            if state is not None:
                # Move to end for LRU
                self._runtime_states.move_to_end(task_id)
                logger.debug(f"Loaded runtime state for task {task_id}")
            return state
    
    def exists_runtime_state(self, task_id: str) -> bool:
        """Check if runtime state exists"""
        with self._lock:
            return task_id in self._runtime_states
    
    # ==================== Session Progress Operations ====================
    
    def save_session_progress(self, task_id: str, progress: Dict[str, Any]) -> bool:
        """Save session progress to memory"""
        try:
            with self._lock:
                self._session_progress[task_id] = progress.copy()
                self._state_timestamps[task_id] = time.time()
                logger.debug(f"Saved session progress for task {task_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to save session progress for {task_id}: {e}")
            return False
    
    def load_session_progress(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Load session progress from memory"""
        with self._lock:
            progress = self._session_progress.get(task_id)
            if progress is not None:
                return progress.copy()
            return None
    
    # ==================== Task Lifecycle Operations ====================
    
    def delete_task_state(self, task_id: str) -> bool:
        """Delete all state for a task"""
        with self._lock:
            existed = task_id in self._runtime_states or task_id in self._session_progress
            self._remove_task_internal(task_id)
            if existed:
                logger.info(f"Deleted state for task {task_id}")
            return existed
    
    def list_active_tasks(self) -> List[str]:
        """List all active task IDs"""
        with self._lock:
            return list(self._runtime_states.keys())
    
    def heartbeat(self, task_id: str, ttl_seconds: int = 300) -> bool:
        """Update task heartbeat"""
        with self._lock:
            self._heartbeats[task_id] = time.time()
            return True
    
    def is_task_alive(self, task_id: str) -> bool:
        """Check if task has recent heartbeat"""
        with self._lock:
            last_heartbeat = self._heartbeats.get(task_id)
            if last_heartbeat is None:
                return False
            return time.time() - last_heartbeat < 300  # 5 minutes default
    
    def get_stale_tasks(self, max_age_seconds: int = 600) -> List[str]:
        """Get tasks with stale heartbeats"""
        now = time.time()
        stale = []
        
        with self._lock:
            for task_id in self._runtime_states:
                last_heartbeat = self._heartbeats.get(task_id, 0)
                if now - last_heartbeat > max_age_seconds:
                    stale.append(task_id)
        
        return stale
    
    # ==================== Distributed Locking ====================
    
    def acquire_lock(self, task_id: str, timeout_seconds: int = 30) -> bool:
        """Acquire exclusive lock for a task"""
        now = time.time()
        
        with self._lock:
            # Check if already locked
            existing_expiry = self._locks.get(task_id)
            if existing_expiry is not None and existing_expiry > now:
                # Still locked
                return False
            
            # Acquire lock
            self._locks[task_id] = now + timeout_seconds
            logger.debug(f"Acquired lock for task {task_id}")
            return True
    
    def release_lock(self, task_id: str) -> bool:
        """Release exclusive lock for a task"""
        with self._lock:
            if task_id in self._locks:
                del self._locks[task_id]
                logger.debug(f"Released lock for task {task_id}")
                return True
            return False
    
    def is_locked(self, task_id: str) -> bool:
        """Check if task is currently locked"""
        now = time.time()
        
        with self._lock:
            expiry = self._locks.get(task_id)
            if expiry is None:
                return False
            if expiry <= now:
                # Lock expired, clean up
                del self._locks[task_id]
                return False
            return True
    
    # ==================== Utility Methods ====================
    
    def clear_all(self) -> bool:
        """Clear all stored state"""
        with self._lock:
            count = len(self._runtime_states)
            self._runtime_states.clear()
            self._session_progress.clear()
            self._heartbeats.clear()
            self._locks.clear()
            self._state_timestamps.clear()
            logger.warning(f"Cleared all state ({count} tasks)")
            return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        with self._lock:
            return {
                "type": "memory",
                "total_tasks": len(self._runtime_states),
                "total_sessions": len(self._session_progress),
                "active_locks": sum(1 for exp in self._locks.values() if exp > time.time()),
                "max_tasks": self.max_tasks,
                "default_ttl_seconds": self.default_ttl_seconds,
            }
    
    def close(self):
        """Stop cleanup thread and release resources"""
        self._stop_cleanup.set()
        if self._cleanup_thread is not None:
            self._cleanup_thread.join(timeout=5)
        logger.info("MemoryStateStore closed")
