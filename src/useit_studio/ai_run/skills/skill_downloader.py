"""
S3 Skill Downloader

从 S3 下载完整的 skill 目录到本地缓存，供 SkillLoader 使用。

S3 路径结构:
    useit.user.demo.storage/
    └── skills/
        └── {user_id}/
            └── {skill_name}/
                ├── SKILL.md
                ├── references/
                └── drawing/_templates/

本地缓存结构:
    .cache/s3_skills/
    └── {user_id}/
        └── {skill_name}/
            ├── SKILL.md
            └── ...

使用示例:
    from useit_studio.ai_run.skills.skill_downloader import get_skill_downloader

    downloader = get_skill_downloader()
    skill_folder, skill_name = downloader.download_skill("skills/uuid/u-channel")
    # skill_folder = ".cache/s3_skills/uuid/"  (parent dir for SkillLoader)
    # skill_name  = "u-channel"
"""

import os
import threading
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_s3_client = None
_lock = threading.Lock()


def _get_s3_client():
    """Lazily initialise a shared boto3 S3 client (singleton)."""
    global _s3_client
    if _s3_client is not None:
        return _s3_client

    with _lock:
        if _s3_client is not None:
            return _s3_client
        try:
            import boto3
            from botocore.config import Config

            config = Config(
                connect_timeout=10,
                read_timeout=30,
                retries={"max_attempts": 3},
            )
            _s3_client = boto3.client(
                "s3",
                region_name=os.getenv("AWS_REGION", "us-west-2"),
                config=config,
            )
            logger.info("[SkillDownloader] S3 client initialized")
        except Exception as e:
            logger.error(f"[SkillDownloader] Failed to init S3 client: {e}")
    return _s3_client


class SkillDownloader:
    """Downloads an entire skill directory tree from S3 into a local cache."""

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        cache_dir: str = ".cache/s3_skills",
    ):
        raw = bucket_name or os.getenv("S3_BUCKET_NAME", "useit.user.demo.storage")
        self.bucket_name = raw.strip("\"'")
        self.cache_dir = os.path.abspath(cache_dir)

    # ------------------------------------------------------------------ #
    # Public helpers                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def is_s3_path(skill_ref: str) -> bool:
        """Return True when *skill_ref* looks like an S3 skill path
        (contains at least one ``/``, e.g. ``skills/{uid}/{name}``)."""
        return "/" in skill_ref

    @staticmethod
    def parse_skill_name(s3_skill_path: str) -> str:
        """Extract the trailing skill name from an S3 path."""
        return s3_skill_path.strip("/").rsplit("/", 1)[-1]

    # ------------------------------------------------------------------ #
    # Core download                                                       #
    # ------------------------------------------------------------------ #

    def download_skill(
        self,
        s3_skill_path: str,
        force: bool = False,
    ) -> Tuple[Optional[str], str]:
        """Download a full skill directory from S3.

        Args:
            s3_skill_path: S3 key prefix, e.g. ``"skills/{user_id}/{skill_name}"``
            force: re-download even when a local cache already exists

        Returns:
            ``(skill_folder, skill_name)``

            * *skill_folder* – the **parent** directory that contains the skill
              (pass this to ``SkillLoader`` / ``SkillCache`` as ``skill_folder``).
              ``None`` when the download failed.
            * *skill_name* – the last segment of the path (``"u-channel"``).
        """
        parts = s3_skill_path.strip("/").split("/")
        if len(parts) < 2:
            logger.warning(
                "[SkillDownloader] Path too short, cannot parse: %s",
                s3_skill_path,
            )
            return None, s3_skill_path

        skill_name = parts[-1]

        # Strip leading "skills/" for local layout:
        #   .cache/s3_skills/{user_id}/{skill_name}/...
        sub_parts = parts[1:] if parts[0] == "skills" else parts
        local_skill_dir = os.path.join(self.cache_dir, *sub_parts)
        local_parent_dir = (
            os.path.join(self.cache_dir, *sub_parts[:-1])
            if len(sub_parts) > 1
            else self.cache_dir
        )

        # Fast-path: already cached
        skill_md = os.path.join(local_skill_dir, "SKILL.md")
        if not force and os.path.exists(skill_md):
            self._touch_cache(local_skill_dir)
            logger.info("[SkillDownloader] Cache hit: %s", local_skill_dir)
            return local_parent_dir, skill_name

        # Need to download
        client = _get_s3_client()
        if client is None:
            logger.error("[SkillDownloader] S3 client not available")
            return None, skill_name

        s3_prefix = s3_skill_path.rstrip("/") + "/"

        try:
            downloaded = 0
            paginator = client.get_paginator("list_objects_v2")

            for page in paginator.paginate(
                Bucket=self.bucket_name, Prefix=s3_prefix
            ):
                for obj in page.get("Contents", []):
                    s3_key = obj["Key"]
                    relative = s3_key[len(s3_prefix):]
                    if not relative:
                        continue

                    local_file = os.path.join(local_skill_dir, relative)
                    os.makedirs(os.path.dirname(local_file), exist_ok=True)
                    client.download_file(self.bucket_name, s3_key, local_file)
                    downloaded += 1
                    logger.debug("[SkillDownloader] %s -> %s", s3_key, local_file)

            if downloaded == 0:
                logger.warning(
                    "[SkillDownloader] No files at s3://%s/%s",
                    self.bucket_name,
                    s3_prefix,
                )
                return None, skill_name

            self._touch_cache(local_skill_dir)
            logger.info(
                "[SkillDownloader] Downloaded %d file(s): s3://%s/%s -> %s",
                downloaded,
                self.bucket_name,
                s3_prefix,
                local_skill_dir,
            )
            return local_parent_dir, skill_name

        except Exception as e:
            logger.error(
                "[SkillDownloader] Download failed s3://%s/%s: %s",
                self.bucket_name,
                s3_prefix,
                e,
            )
            return None, skill_name

    # ------------------------------------------------------------------ #
    # LRU touch                                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _touch_cache(path: str) -> None:
        """通知 CacheManager 目录被访问，更新 LRU 时间戳"""
        try:
            from useit_studio.ai_run.utils.cache_manager import get_cache_manager
            get_cache_manager().touch(path)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Cache management                                                    #
    # ------------------------------------------------------------------ #

    def is_cached(self, s3_skill_path: str) -> bool:
        """Check whether a skill has already been downloaded."""
        parts = s3_skill_path.strip("/").split("/")
        sub_parts = parts[1:] if parts[0] == "skills" else parts
        local_dir = os.path.join(self.cache_dir, *sub_parts)
        return os.path.exists(os.path.join(local_dir, "SKILL.md"))

    def invalidate(self, s3_skill_path: str) -> None:
        """Remove cached files so the next call re-downloads."""
        import shutil

        parts = s3_skill_path.strip("/").split("/")
        sub_parts = parts[1:] if parts[0] == "skills" else parts
        local_dir = os.path.join(self.cache_dir, *sub_parts)

        if os.path.isdir(local_dir):
            shutil.rmtree(local_dir, ignore_errors=True)
            logger.info("[SkillDownloader] Invalidated: %s", local_dir)


# ------------------------------------------------------------------ #
# Module-level singleton                                              #
# ------------------------------------------------------------------ #

_default_downloader: Optional[SkillDownloader] = None


def get_skill_downloader(
    cache_dir: Optional[str] = None,
) -> SkillDownloader:
    """Get (or create) the global SkillDownloader singleton."""
    global _default_downloader
    if _default_downloader is None:
        with _lock:
            if _default_downloader is None:
                _default_downloader = SkillDownloader(
                    cache_dir=cache_dir
                    or os.getenv("S3_SKILL_CACHE_DIR", ".cache/s3_skills"),
                )
    return _default_downloader
