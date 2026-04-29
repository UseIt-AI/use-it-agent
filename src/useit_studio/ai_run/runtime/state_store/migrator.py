"""
State Migrator

Handles migration of state data between schema versions.
When the runtime architecture changes, add a new migration function
to upgrade old data to the new format.

Usage:
    # Automatically migrate data to current version
    migrated_data = StateMigrator.migrate(old_data)
    
    # Check current version
    version = StateMigrator.CURRENT_VERSION
"""

from typing import Dict, Any, Optional, List
import time
import logging

logger = logging.getLogger(__name__)


class StateMigrator:
    """
    State data version migrator.
    
    Handles forward migration of state data when schema changes.
    Each version bump requires a corresponding migration function.
    
    Migration functions are named: _migrate_vX_to_vY
    They are called in sequence to upgrade data step by step.
    """
    
    # Current schema version - increment when making breaking changes
    CURRENT_VERSION = 1
    
    @classmethod
    def migrate(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migrate data to current schema version.
        
        Automatically detects data version and applies necessary migrations.
        
        Args:
            data: State data (may be any version)
            
        Returns:
            Data migrated to CURRENT_VERSION
        """
        # Get current version from data
        meta = data.get("_meta", {})
        version = meta.get("schema_version", 0)
        
        if version == cls.CURRENT_VERSION:
            # Already at current version
            return data
        
        if version > cls.CURRENT_VERSION:
            # Data is from future version - can't downgrade
            logger.warning(
                f"Data version {version} is newer than current {cls.CURRENT_VERSION}. "
                "Cannot downgrade, returning as-is."
            )
            return data
        
        logger.info(f"Migrating state data from v{version} to v{cls.CURRENT_VERSION}")
        
        # Apply migrations sequentially
        while version < cls.CURRENT_VERSION:
            next_version = version + 1
            migrate_fn = getattr(cls, f"_migrate_v{version}_to_v{next_version}", None)
            
            if migrate_fn is None:
                logger.error(f"Missing migration function: _migrate_v{version}_to_v{next_version}")
                raise ValueError(f"Cannot migrate from v{version} to v{next_version}")
            
            logger.debug(f"Applying migration: v{version} -> v{next_version}")
            data = migrate_fn(data)
            version = next_version
        
        return data
    
    @classmethod
    def get_version(cls, data: Dict[str, Any]) -> int:
        """
        Get schema version from data.
        
        Args:
            data: State data
            
        Returns:
            Schema version (0 if not versioned)
        """
        return data.get("_meta", {}).get("schema_version", 0)
    
    @classmethod
    def is_current_version(cls, data: Dict[str, Any]) -> bool:
        """
        Check if data is at current schema version.
        
        Args:
            data: State data
            
        Returns:
            True if at current version
        """
        return cls.get_version(data) == cls.CURRENT_VERSION
    
    # ==================== Migration Functions ====================
    # Add new migration functions here when schema changes
    
    @classmethod
    def _migrate_v0_to_v1(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migrate from v0 (unversioned) to v1.
        
        v0: Raw state data without metadata wrapper
        v1: Wrapped with _meta and payload structure
        
        Changes:
        - Add _meta with schema_version
        - Wrap existing data in payload
        """
        # Check if already has _meta (shouldn't happen but be safe)
        if "_meta" in data and "payload" in data:
            data["_meta"]["schema_version"] = 1
            return data
        
        # Wrap unversioned data
        migrated = {
            "_meta": {
                "schema_version": 1,
                "migrated_at": time.time(),
                "migrated_from": 0,
            },
            "payload": data
        }
        
        logger.info("Migrated unversioned data to v1 format")
        return migrated
    
    # ==================== Future Migration Templates ====================
    # Uncomment and modify when adding new versions
    
    # @classmethod
    # def _migrate_v1_to_v2(cls, data: Dict[str, Any]) -> Dict[str, Any]:
    #     """
    #     Migrate from v1 to v2.
    #     
    #     Changes:
    #     - Example: Rename field 'foo' to 'bar'
    #     - Example: Add new required field 'baz' with default
    #     """
    #     payload = data["payload"]
    #     
    #     # Example: Rename field in state
    #     state = payload.get("state", {})
    #     if "oldFieldName" in state:
    #         state["newFieldName"] = state.pop("oldFieldName")
    #     
    #     # Example: Add new field with default
    #     if "newRequiredField" not in state:
    #         state["newRequiredField"] = "default_value"
    #     
    #     # Example: Transform nested structure
    #     for node in state.get("executionTree", []):
    #         # Add new field to each node
    #         if "newNodeField" not in node:
    #             node["newNodeField"] = None
    #     
    #     # Update version
    #     data["_meta"]["schema_version"] = 2
    #     data["_meta"]["migrated_at"] = time.time()
    #     data["_meta"]["migrated_from"] = 1
    #     
    #     return data
    
    # @classmethod
    # def _migrate_v2_to_v3(cls, data: Dict[str, Any]) -> Dict[str, Any]:
    #     """
    #     Migrate from v2 to v3.
    #     
    #     Changes:
    #     - Describe changes here
    #     """
    #     payload = data["payload"]
    #     
    #     # Apply transformations...
    #     
    #     data["_meta"]["schema_version"] = 3
    #     data["_meta"]["migrated_at"] = time.time()
    #     data["_meta"]["migrated_from"] = 2
    #     
    #     return data


class MigrationError(Exception):
    """Raised when migration fails"""
    pass
