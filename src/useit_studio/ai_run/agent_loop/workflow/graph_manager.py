from typing import Any, Dict, List, Optional

from useit_studio.ai_run.utils.logger_utils import LoggerUtils

logger = LoggerUtils(component_name="graph_manager")


class GraphManager:
    """
    本地工作流图管理：仅从内存中的 ``graph_definition`` 构建（无远程数据库）。
    未传入定义时使用默认的 start → agent → end 图。
    """

    def __init__(
        self,
        workflow_id: str,
        task_id: Optional[str] = None,
        graph_definition: Optional[Dict[str, Any]] = None,
    ):
        self.workflow_id = workflow_id
        self.task_id = task_id
        self.logger = logger

        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, Any]] = []
        self.adjacency_list: Dict[str, List[Dict[str, Any]]] = {}

        if graph_definition is None:
            from useit_studio.ai_run.config.default_standalone_workflow import get_default_minimal_workflow

            graph_definition = get_default_minimal_workflow()
        self.logger.logger.info("GraphManager: ingesting graph_definition (local OSS)")
        self._ingest_graph_payload(graph_definition)

    def _ingest_graph_payload(self, graph_data: Dict[str, Any]) -> None:
        """Populate nodes, edges, and adjacency_list from a workflow definition dict."""
        for node_data in graph_data.get("nodes", []):
            nid = node_data.get("id")
            if nid:
                self.nodes[nid] = node_data

        self.edges = graph_data.get("edges", [])
        for edge in self.edges:
            source_id = edge.get("source")
            if not source_id:
                continue
            if source_id not in self.adjacency_list:
                self.adjacency_list[source_id] = []
            self.adjacency_list[source_id].append(edge)

        self.logger.logger.info(
            f"Workflow graph ingested: {len(self.nodes)} nodes, {len(self.edges)} edges"
        )

    def _find_start_node_id(self) -> Optional[str]:
        """Find the start node ID"""
        for node_id, node_data in self.nodes.items():
            if node_data.get("data", {}).get("type") == "start":
                return node_id
        return None

    def get_ordered_nodes(self) -> List[Dict[str, Any]]:
        """
        Gets a topologically sorted list of all nodes in the graph.
        It performs a traversal from all 'start' nodes and then adds any unvisited nodes.
        This ensures all nodes, including those in disconnected subgraphs (like loops), are included.
        
        Returns:
            List[Dict[str, Any]]: A flat list of all nodes in the graph, ordered for execution.
        """
        
        # Find all start nodes
        start_node_ids = [node_id for node_id, node in self.nodes.items() if node.get("data", {}).get("type") == "start"]

        if not start_node_ids:
            # If no start node, return all nodes in arbitrary order
            return list(self.nodes.values())

        initial_ordered_nodes = []
        visited = set()

        # First, traverse the main graph flow
        for start_node_id in start_node_ids:
            if start_node_id not in visited:
                self._traverse_from_node(start_node_id, initial_ordered_nodes, visited)
        
        # Now, create the final list, inserting loop children at the right place
        final_ordered_nodes = []
        for node in initial_ordered_nodes:
            final_ordered_nodes.append(node)
            # If we find a loop, traverse its children and insert them right after
            if node.get("type") == "loop":
                loop_start_node_id = node.get("data", {}).get("start_node_id")
                if loop_start_node_id and loop_start_node_id not in visited:
                    self._traverse_from_node(loop_start_node_id, final_ordered_nodes, visited)

        # Add any remaining nodes that were not visited (e.g., in completely disconnected subgraphs)
        for node_id, node in self.nodes.items():
            if node_id not in visited:
                final_ordered_nodes.append(self._create_base_node_info_from_raw(node))

        return final_ordered_nodes

    def get_nodes_dict(self) -> Dict[str, Dict[str, Any]]:
        """
        Gets all nodes in the graph as a dictionary.
        Similar to get_ordered_nodes but returns a dict where key is node_id and value is node info.
        
        Returns:
            Dict[str, Dict[str, Any]]: A dictionary mapping node IDs to their node information.
        """
        nodes_dict = {}
        
        # Get all ordered nodes using the existing logic
        ordered_nodes = self.get_ordered_nodes()
        
        # Convert the list to a dictionary
        for node in ordered_nodes:
            node_id = node.get("id")
            if node_id:
                nodes_dict[node_id] = node
        
        return nodes_dict

    def _traverse_from_node(self, node_id: str, ordered_nodes: List, visited: set):
        """
        Performs a DFS traversal to collect nodes in order.
        """
        if node_id in visited:
            return
        
        node = self.nodes.get(node_id)
        if not node:
            return
            
        visited.add(node_id)
        
        # The node that is currently being processed is added before its children are processed.
        ordered_nodes.append(self._create_base_node_info_from_raw(node))

        # Recur for all the vertices adjacent to this vertex
        for edge in self.adjacency_list.get(node_id, []):
            target_id = edge.get("target")
            if target_id and target_id not in visited:
                self._traverse_from_node(target_id, ordered_nodes, visited)

    def _create_base_node_info_from_raw(self, node_data: Dict) -> Dict[str, Any]:
        """Creates a standardized node info dictionary from the raw node data stored in the manager."""
        node_id = node_data.get("id")
        data = node_data.get("data", {})
        node_type = data.get("type")

        # Reuse existing logic to build the detailed info dict
        milestone_info = self._create_base_node_info(node_id, node_type, data, loop_info=data.get("loop_info"))

        if node_type == "computer-use":
            milestone_info.update(self._create_milestone_info(node_id, node_type, data, loop_info=data.get("loop_info")))

        return milestone_info

    def _create_milestone_info(self, node_id: str, node_type: str, node_data: Dict, loop_info: Optional[Dict]) -> Dict[str, Any]:
        """Create milestone node information"""
        detailed_steps = node_data.get("detailed_steps", [])
        trajectories = []

        for i, step_detail in enumerate(detailed_steps):
            caption_data = step_detail.get("caption", {})
            trajectory_item = {
                "step_idx": step_detail.get("step_idx", i + 1),
                "caption": {
                    "action": caption_data.get("action", "Missing action"),
                    "is_icon": caption_data.get("is_icon", False)
                },
                "icon_info": step_detail.get("icon_info") if caption_data.get("is_icon", False) else None
            }
            trajectories.append(trajectory_item)

        milestone_info = self._create_base_node_info(node_id, node_type, node_data, loop_info)

        # clean steps from graph
        milestone_steps = node_data.get("steps", [])
        clean_milestone_steps = []
        if isinstance(milestone_steps, list):
            for step in milestone_steps:
                if isinstance(step, dict):
                    clean_milestone_steps.append(step.get("content", step))
                else:
                    clean_milestone_steps.append(step)

        milestone_info.update({
            "description": node_data.get("description", ""),
            "milestone_steps": clean_milestone_steps,
            "trajectories": trajectories,
        })
        return milestone_info

    def _create_base_node_info(self, node_id: str, node_type: str, node_data: Dict, loop_info: Optional[Dict]) -> Dict[str, Any]:
        """Create base node information"""
        raw_node = self.nodes.get(node_id, {})
        # 支持 parentId 和 parentNode 两种字段名
        parent_id = raw_node.get("parentId") or raw_node.get("parentNode")
        info = {
            "id": node_id,
            "type": node_type,
            "title": node_data.get("title", f"Untitled {node_type} Node"),
            "data": node_data,
            "parentId": parent_id,
        }
        if loop_info:
            info["loop_info"] = loop_info.copy()
        return info

    def get_milestone_by_id(self, milestone_id: str, ordered_milestones: Optional[List[Dict]] = None) -> Optional[Dict]:
        """
        Get a specific milestone by ID.
        If an ordered_milestones list is provided, search within that list.
        Otherwise, fetch directly from the internal nodes dictionary for efficiency.
        """
        if ordered_milestones:
            for milestone in ordered_milestones:
                if milestone["id"] == milestone_id:
                    return milestone
            return None
        
        # If no list is provided, fetch directly from the source for efficiency
        node_data = self.nodes.get(milestone_id)
        if not node_data:
            return None
        
        return self._create_base_node_info_from_raw(node_data)

    def get_milestone_step_icon(self, milestone_id: str, step_idx: int, 
                              ordered_milestones: Optional[List[Dict]] = None) -> Optional[str]:
        """Get the icon name for a milestone step"""
        milestone = self.get_milestone_by_id(milestone_id, ordered_milestones)
        if not milestone:
            return None

        trajectories = milestone.get("trajectories", [])
        for trajectory_item in trajectories:
            if trajectory_item.get("milestone_step_idx") == step_idx:
                if (trajectory_item.get("caption", {}).get("is_icon") and 
                    trajectory_item.get("icon_info")):
                    try:
                        return trajectory_item["icon_info"][0]["name"]
                    except (IndexError, KeyError, TypeError):
                        return None
                return None
        return None 
    
    def get_milestone_in_context(self, milestone_id: str) -> Optional[str]:
        pass
    
    def get_all_node_types(self) -> List[str]:
        pass
    
    @classmethod
    def clear_cache(cls) -> None:
        """保留 API 兼容；本地构建不再使用工作流定义缓存。"""
        logger.logger.info("GraphManager.clear_cache (no-op)")

    @classmethod
    def clear_workflow_cache(cls, workflow_id: str, task_id: Optional[str] = None) -> None:
        pass

    @classmethod
    def clear_task_cache(cls, task_id: str) -> None:
        pass

    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        return {
            "total_entries": 0,
            "note": "workflow definition cache disabled in local OSS build",
        }

    @classmethod
    def set_cache_ttl(cls, ttl_seconds: float) -> None:
        logger.logger.info("GraphManager.set_cache_ttl ignored (local OSS build)")