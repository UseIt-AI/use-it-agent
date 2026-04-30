"""
State Serializer

Handles serialization and deserialization of state data with version management.
Provides a unified interface for converting state objects to/from storage format.

Features:
- Automatic version tagging on serialize
- Automatic migration on deserialize
- Support for different serialization formats (JSON, MessagePack)
- Compression for large payloads
"""

import json
import time
import zlib
import logging
from typing import Dict, Any, Optional, Union
from enum import Enum

from .migrator import StateMigrator

logger = logging.getLogger(__name__)


class SerializationFormat(str, Enum):
    """Supported serialization formats"""
    JSON = "json"
    JSON_COMPRESSED = "json_compressed"
    # Future: MSGPACK = "msgpack"


class StateSerializer:
    """
    State serializer with version management.
    
    Wraps state data with metadata and handles serialization/deserialization.
    Automatically applies migrations when loading old data.
    
    Usage:
        serializer = StateSerializer()
        
        # Serialize state
        data_bytes = serializer.serialize(state_dict)
        
        # Deserialize (auto-migrates if needed)
        state_dict = serializer.deserialize(data_bytes)
    """
    
    # Compression threshold (bytes) - compress if payload larger
    COMPRESSION_THRESHOLD = 10 * 1024  # 10KB
    
    def __init__(
        self,
        format: SerializationFormat = SerializationFormat.JSON,
        auto_compress: bool = True,
        compression_level: int = 6,
    ):
        """
        Initialize serializer.
        
        Args:
            format: Serialization format to use
            auto_compress: Whether to auto-compress large payloads
            compression_level: zlib compression level (1-9)
        """
        self.format = format
        self.auto_compress = auto_compress
        self.compression_level = compression_level
    
    def serialize(
        self,
        payload: Dict[str, Any],
        include_timestamp: bool = True,
    ) -> bytes:
        """
        Serialize state data to bytes.
        
        Wraps payload with metadata including schema version.
        
        Args:
            payload: State data dictionary
            include_timestamp: Whether to include timestamps in metadata
            
        Returns:
            Serialized bytes
        """
        # Build wrapped data structure
        wrapped = {
            "_meta": {
                "schema_version": StateMigrator.CURRENT_VERSION,
                "serializer": self.format.value,
            },
            "payload": payload,
        }
        
        if include_timestamp:
            wrapped["_meta"]["created_at"] = time.time()
        
        # Serialize to JSON
        json_str = json.dumps(wrapped, ensure_ascii=False, separators=(',', ':'))
        data_bytes = json_str.encode('utf-8')
        
        # Optionally compress
        if self.auto_compress and len(data_bytes) > self.COMPRESSION_THRESHOLD:
            compressed = zlib.compress(data_bytes, self.compression_level)
            
            # Only use compressed if actually smaller
            if len(compressed) < len(data_bytes):
                logger.debug(
                    f"Compressed state: {len(data_bytes)} -> {len(compressed)} bytes "
                    f"({100 * len(compressed) / len(data_bytes):.1f}%)"
                )
                # Prepend marker byte to indicate compression
                return b'\x01' + compressed
        
        # Prepend marker byte to indicate no compression
        return b'\x00' + data_bytes
    
    def deserialize(
        self,
        data: Union[bytes, str, Dict[str, Any]],
        auto_migrate: bool = True,
    ) -> Dict[str, Any]:
        """
        Deserialize state data from bytes.
        
        Automatically detects format and applies migrations if needed.
        
        Args:
            data: Serialized data (bytes, JSON string, or already parsed dict)
            auto_migrate: Whether to auto-migrate old versions
            
        Returns:
            Deserialized payload dictionary (without wrapper)
            
        Raises:
            ValueError: If data format is invalid
        """
        # Handle already-parsed dict
        if isinstance(data, dict):
            wrapped = data
        elif isinstance(data, str):
            wrapped = json.loads(data)
        elif isinstance(data, bytes):
            wrapped = self._deserialize_bytes(data)
        else:
            raise ValueError(f"Unsupported data type: {type(data)}")
        
        # Check if data has our wrapper format
        if "_meta" not in wrapped or "payload" not in wrapped:
            # Legacy format - wrap it
            logger.debug("Detected legacy format, wrapping data")
            wrapped = {
                "_meta": {"schema_version": 0},
                "payload": wrapped,
            }
        
        # Migrate if needed
        if auto_migrate:
            wrapped = StateMigrator.migrate(wrapped)
        
        # Return just the payload
        return wrapped["payload"]
    
    def _deserialize_bytes(self, data: bytes) -> Dict[str, Any]:
        """
        Deserialize bytes, handling compression.
        
        Args:
            data: Raw bytes (possibly compressed)
            
        Returns:
            Parsed dictionary
        """
        if len(data) == 0:
            raise ValueError("Empty data")
        
        # Check compression marker
        marker = data[0]
        payload = data[1:]
        
        if marker == 0x01:
            # Compressed
            try:
                payload = zlib.decompress(payload)
            except zlib.error as e:
                raise ValueError(f"Failed to decompress data: {e}")
        elif marker == 0x00:
            # Not compressed
            pass
        else:
            # No marker - legacy format, try as-is
            payload = data
        
        # Parse JSON
        try:
            return json.loads(payload.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Failed to parse JSON: {e}")
    
    def get_metadata(self, data: Union[bytes, str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract metadata from serialized data without full deserialization.
        
        Args:
            data: Serialized data
            
        Returns:
            Metadata dictionary
        """
        if isinstance(data, dict):
            return data.get("_meta", {})
        
        # Need to deserialize to get metadata
        if isinstance(data, str):
            parsed = json.loads(data)
        elif isinstance(data, bytes):
            parsed = self._deserialize_bytes(data)
        else:
            return {}
        
        return parsed.get("_meta", {})
    
    def get_version(self, data: Union[bytes, str, Dict[str, Any]]) -> int:
        """
        Get schema version from serialized data.
        
        Args:
            data: Serialized data
            
        Returns:
            Schema version (0 if not found)
        """
        meta = self.get_metadata(data)
        return meta.get("schema_version", 0)


# Default serializer instance
default_serializer = StateSerializer()


def serialize_state(payload: Dict[str, Any]) -> bytes:
    """Convenience function using default serializer"""
    return default_serializer.serialize(payload)


def deserialize_state(data: Union[bytes, str, Dict[str, Any]]) -> Dict[str, Any]:
    """Convenience function using default serializer"""
    return default_serializer.deserialize(data)
