"""
Skills 模块

Skill 是给 AI 看的"说明书":
- 只自动加载 SKILL.md (目录/索引)
- 其他文件由 AI 按需通过 tools 读取
- SkillFileReader 管理文件按需读取和状态持久化
- skill_prompts 提供可复用的 prompt 片段
"""

from .skill_loader import SkillLoader, SkillContent, SkillMetadata, SkillCache
from .skill_file_reader import SkillFileReader, ReadResult
from .skill_prompts import skill_system_actions, skill_decision_steps, skill_user_fragments
from .skill_downloader import SkillDownloader, get_skill_downloader

__all__ = [
    # Loader
    'SkillLoader', 'SkillContent', 'SkillMetadata', 'SkillCache',
    # Downloader (S3)
    'SkillDownloader', 'get_skill_downloader',
    # File Reader
    'SkillFileReader', 'ReadResult',
    # Prompts
    'skill_system_actions', 'skill_decision_steps', 'skill_user_fragments',
]
