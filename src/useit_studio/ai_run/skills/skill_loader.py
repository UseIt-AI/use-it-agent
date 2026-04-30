"""
Skill Loader - 负责 skill 的发现和加载

核心原则:
1. 只加载 SKILL.md - 其他文件按需读取
2. 提供 base_dir - 让 AI 知道去哪里找文件
3. 不预加载资源 - 避免浪费 tokens
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pathlib import Path
import os
import logging

logger = logging.getLogger(__name__)


@dataclass
class SkillMetadata:
    """Skill 元数据(从 YAML frontmatter 解析)"""
    name: str
    description: str
    context: Optional[str] = None  # python, javascript, etc
    license: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'name': self.name,
            'description': self.description,
            'context': self.context,
            'license': self.license,
        }


@dataclass
class SkillContent:
    """
    加载后的 Skill 内容

    ⚠️ 重要: 只包含 SKILL.md 的内容!

    其他文件(scripts, references 等)不会预加载,
    而是让 AI 通过 read file tool 按需读取。
    """
    metadata: SkillMetadata
    content: str  # SKILL.md 的 markdown 内容(不含 frontmatter)
    base_dir: Path  # skill 根目录 - AI 可以据此找到其他文件

    def get_resource_path(self, relative_path: str) -> str:
        """
        获取资源的绝对路径(字符串格式)

        这个路径会被提供给 AI, AI 可以用 read_file tool 读取。

        Args:
            relative_path: 相对路径, 如 "scripts/helper.py"

        Returns:
            绝对路径字符串
        """
        return str(self.base_dir / relative_path)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典(用于序列化)"""
        return {
            'metadata': self.metadata.to_dict(),
            'content': self.content,
            'base_dir': str(self.base_dir),
        }


class SkillLoader:
    """
    Skill 加载器

    只加载 SKILL.md, 不预加载其他资源。
    """

    @staticmethod
    def get_search_dirs(
        project_root: Optional[str] = None,
        skill_folder: Optional[str] = None,
    ) -> List[Path]:
        """
        获取 skill 搜索目录(优先级顺序)

        Args:
            project_root: 项目根目录（默认：当前工作目录）
            skill_folder: 自定义 skill 根目录（优先级最高）

        Returns:
            搜索路径列表，按优先级排序
        """
        if project_root is None:
            project_root = os.getcwd()

        home = Path.home()
        project = Path(project_root)

        search_dirs = []

        # 如果提供了 skill_folder，优先搜索
        if skill_folder:
            custom = Path(skill_folder)
            search_dirs.extend([
                custom,                          # 0. 直接在 skill_folder 下（新增，支持 SKILLS/skill-{id}/ 格式）
                custom / ".agent" / "skills",    # 1. 自定义 .agent
                custom / ".claude" / "skills",   # 2. 自定义 .claude
            ])

        # 标准搜索路径
        search_dirs.extend([
            project / ".agent" / "skills",      # 3. 项目 .agent
            home / ".agent" / "skills",          # 4. 全局 .agent
            project / ".claude" / "skills",     # 5. 项目 .claude
            home / ".claude" / "skills",         # 6. 全局 .claude
        ])

        return search_dirs

    @staticmethod
    def find_skill(
        skill_name: str,
        project_root: Optional[str] = None,
        skill_folder: Optional[str] = None,
    ) -> Optional[Path]:
        """
        查找 skill 目录

        Args:
            skill_name: skill 名称
            project_root: 项目根目录
            skill_folder: 自定义 skill 根目录（优先）

        Returns:
            skill 目录的 Path，如果未找到返回 None
        """
        search_dirs = SkillLoader.get_search_dirs(project_root, skill_folder)

        for base_dir in search_dirs:
            if not base_dir.exists():
                continue

            skill_dir = base_dir / skill_name
            skill_md = skill_dir / "SKILL.md"

            if skill_md.exists() and skill_md.is_file():
                logger.debug(f"Found skill '{skill_name}' at: {skill_dir}")
                return skill_dir

        logger.debug(f"Skill '{skill_name}' not found in search paths")
        return None

    @staticmethod
    def load_skill(
        skill_name: str,
        project_root: Optional[str] = None,
        skill_folder: Optional[str] = None,
    ) -> Optional[SkillContent]:
        """
        加载 skill

        ⚠️ 只加载 SKILL.md, 不加载其他文件!

        Args:
            skill_name: skill 名称
            project_root: 项目根目录（向后兼容）
            skill_folder: 自定义 skill 根目录（优先级高于 project_root）

        Returns:
            SkillContent 对象(只包含 SKILL.md 内容)

        加载优先级:
        1. skill_folder/.agent/skills/skill_name/
        2. skill_folder/.claude/skills/skill_name/
        3. project_root/.agent/skills/skill_name/（标准路径）
        4. ~/.agent/skills/skill_name/（全局路径）
        """
        skill_dir = SkillLoader.find_skill(skill_name, project_root, skill_folder)
        if not skill_dir:
            return None

        try:
            # 只读取 SKILL.md
            skill_md_path = skill_dir / "SKILL.md"
            content = skill_md_path.read_text(encoding='utf-8')

            # 解析 YAML frontmatter
            metadata, markdown_content = SkillLoader._parse_frontmatter(content, skill_name)

            logger.info(
                f"Loaded skill: {skill_name} from {skill_dir}\n"
                f"  (Only SKILL.md is loaded. Other files will be read by AI via tools.)"
            )

            return SkillContent(
                metadata=metadata,
                content=markdown_content,
                base_dir=skill_dir,
            )

        except Exception as e:
            logger.error(f"Failed to load skill '{skill_name}': {e}")
            return None

    @staticmethod
    def _parse_frontmatter(content: str, skill_name: str) -> tuple:
        """解析 YAML frontmatter"""
        import yaml

        if not content.startswith('---'):
            logger.warning(f"Skill '{skill_name}' has no YAML frontmatter")
            return SkillMetadata(name=skill_name, description=""), content

        parts = content.split('---', 2)
        if len(parts) < 3:
            logger.warning(f"Skill '{skill_name}' has malformed frontmatter")
            return SkillMetadata(name=skill_name, description=""), content

        yaml_text = parts[1].strip()
        markdown_content = parts[2].strip()

        try:
            metadata_dict = yaml.safe_load(yaml_text) or {}
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML for '{skill_name}': {e}")
            metadata_dict = {}

        metadata = SkillMetadata(
            name=metadata_dict.get('name', skill_name),
            description=metadata_dict.get('description', ''),
            context=metadata_dict.get('context'),
            license=metadata_dict.get('license'),
        )

        return metadata, markdown_content

    @staticmethod
    def list_all_skills(
        project_root: Optional[str] = None,
        skill_folder: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        列出所有可用的 skills

        Args:
            project_root: 项目根目录
            skill_folder: 自定义 skill 根目录

        Returns:
            skills 列表，每个 skill 包含 name, description, location, path
        """
        search_dirs = SkillLoader.get_search_dirs(project_root, skill_folder)
        skills = []
        seen_names = set()

        for base_dir in search_dirs:
            if not base_dir.exists():
                continue

            if project_root and str(base_dir).startswith(str(Path(project_root))):
                location = "project"
            else:
                location = "global"

            for skill_dir in base_dir.iterdir():
                if not skill_dir.is_dir():
                    continue

                skill_md = skill_dir / "SKILL.md"
                if not skill_md.exists():
                    continue

                skill_name = skill_dir.name
                if skill_name in seen_names:
                    continue

                seen_names.add(skill_name)

                try:
                    content = skill_md.read_text(encoding='utf-8')
                    metadata, _ = SkillLoader._parse_frontmatter(content, skill_name)

                    skills.append({
                        'name': skill_name,
                        'description': metadata.description,
                        'location': location,
                        'path': str(skill_dir),
                    })
                except Exception as e:
                    logger.warning(f"Failed to read skill '{skill_name}': {e}")

        return skills


class SkillCache:
    """
    全局 skill 缓存(单例)

    缓存已加载的 SKILL.md 内容。
    """
    _instance = None
    _cache: Dict[str, Optional[SkillContent]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_skill(
        self,
        skill_name: str,
        project_root: Optional[str] = None,
        skill_folder: Optional[str] = None,
    ) -> Optional[SkillContent]:
        """
        获取 skill(带缓存)

        Args:
            skill_name: skill 名称
            project_root: 项目根目录
            skill_folder: 自定义 skill 根目录（优先级高）

        Returns:
            SkillContent 或 None
        """
        # 缓存 key 包含 skill_folder 以区分不同来源的 skill
        cache_key = f"{skill_folder or project_root or os.getcwd()}:{skill_name}"

        if cache_key not in self._cache:
            skill = SkillLoader.load_skill(skill_name, project_root, skill_folder)
            self._cache[cache_key] = skill

        return self._cache.get(cache_key)

    def clear(self):
        """清空缓存"""
        self._cache.clear()

    def invalidate(
        self,
        skill_name: str,
        project_root: Optional[str] = None,
        skill_folder: Optional[str] = None,
    ):
        """
        使某个 skill 的缓存失效

        Args:
            skill_name: skill 名称
            project_root: 项目根目录
            skill_folder: 自定义 skill 根目录
        """
        cache_key = f"{skill_folder or project_root or os.getcwd()}:{skill_name}"
        self._cache.pop(cache_key, None)
