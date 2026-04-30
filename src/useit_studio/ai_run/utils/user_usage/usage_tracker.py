"""
Usage Tracker Module

This module handles both user token usage tracking and cost calculation.
It combines file persistence, usage aggregation, and cost calculation in one unified class.

File Structure:
{USER_USAGE_CACHE_ROOT_DIR}/
└── {user_id}/
    └── {task_id}/
        └── usage_summary.json     # Cumulative usage for this task

Usage:
    usage_tracker = UsageTracker(cache_dir)
    usage_tracker.record_usage_with_cost(user_id, task_id, workflow_id, node_id, node_type, token_usage)
"""

import os
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

from useit_studio.ai_run.utils.logger_utils import LoggerUtils
from useit_studio.ai_run.user_usage.model_pricing import ModelPricing, model_pricing_dict


@dataclass
class CostBreakdown:
    """Cost breakdown for a specific usage calculation."""
    total_cost_usd: float
    total_tokens: int
    model_costs: Dict[str, float]  # {"gpt-4o": 2.50, "claude-3.5": 1.80}
    model_tokens: Dict[str, int]   # {"gpt-4o": 1500, "claude-3.5": 800}
    calculation_timestamp: str


@dataclass
class UserTaskUsageSummary:
    """Cumulative usage summary for a user's task."""
    user_id: str
    task_id: str
    workflow_id: str
    total_tokens: int
    model_breakdown: Dict[str, int]  # {"gpt-4o": 15000, "oai-operator": 8000}
    total_cost_usd: float  # Total cost for this task
    chat_rounds: int  # Number of chat rounds (replaces run_count)
    created_at: str
    updated_at: str


class UsageTracker:
    """Unified usage tracker that handles both token usage tracking and cost calculation."""
    
    def __init__(self, user_usage_cache_root_dir: str, logger: Optional[LoggerUtils] = None):
        self.user_usage_cache_root_dir = user_usage_cache_root_dir
        self.logger = logger or LoggerUtils(component_name="UsageTracker")
        
        # Ensure root directory exists
        os.makedirs(user_usage_cache_root_dir, exist_ok=True)
        
        # Initialize cost tracking
        self.model_pricing = self._get_pricing()
        self.pricing_last_updated = "2025-08-19"  # UPDATE THIS DATE
    
    def _get_pricing(self) -> Dict[str, ModelPricing]:
        """Get pricing data for different models.
        """
        return model_pricing_dict
    
    # ============================================================================
    # COST CALCULATION METHODS
    # ============================================================================
    
    def calculate_cost(self, token_usage: Dict[str, int]) -> CostBreakdown:
        """Calculate cost breakdown for given token usage.
        
        Args:
            token_usage: Dictionary of token usage by model {"gpt-4o": 1500, "oai-operator": 800}
        
        Returns:
            CostBreakdown with detailed cost information
        """
        model_costs = {}
        total_cost = 0.0
        total_tokens = 0
        
        for model_name, token_count in token_usage.items():
            # Get pricing for this model
            if model_name in self.model_pricing:
                pricing = self.model_pricing[model_name]
            else:
                # Use unknown model pricing as fallback
                pricing = self.model_pricing["unknown"]
                if self.logger:
                    self.logger.logger.warning(f"No pricing found for model '{model_name}', using default pricing")
            
            # Calculate cost for this model
            cost = (token_count / 1000000.0) * pricing.average_cost_per_1m_tokens
            model_costs[model_name] = round(cost, 6)  # Round to 6 decimal places for precision
            total_cost += cost
            total_tokens += token_count
        
        return CostBreakdown(
            total_cost_usd=round(total_cost, 6),
            total_tokens=total_tokens,
            model_costs=model_costs,
            model_tokens=token_usage,
            calculation_timestamp=datetime.now(timezone(timedelta(hours=8))).isoformat()
        )
    
    def calculate_cost_with_details(self, token_usage: Dict[str, int]) -> Dict[str, Any]:
        """Calculate cost with detailed breakdown and pricing information.
        
        Returns:
            Dictionary with cost breakdown, pricing details
        """
        cost_breakdown = self.calculate_cost(token_usage)
        
        # Add detailed pricing information
        pricing_details = {}
        
        for model_name, token_count in token_usage.items():
            if model_name in self.model_pricing:
                pricing = self.model_pricing[model_name]
                pricing_details[model_name] = {
                    "tokens": token_count,
                    "cost_usd": cost_breakdown.model_costs[model_name],
                    "pricing_per_1m_tokens": pricing.average_cost_per_1m_tokens,
                    "cost_calculation": f"({token_count} tokens / 1m) * ${pricing.average_cost_per_1m_tokens:.6f}"
                }
            else:
                pricing = self.model_pricing["unknown"]
                pricing_details[model_name] = {
                    "tokens": token_count,
                    "cost_usd": cost_breakdown.model_costs[model_name],
                    "pricing_per_1m_tokens": pricing.average_cost_per_1m_tokens,
                    "cost_calculation": f"({token_count} tokens / 1m) * ${pricing.average_cost_per_1m_tokens:.6f} (DEFAULT PRICING)",
                    "warning": "Using default pricing - model not in pricing database"
                }
        
        return {
            "cost_breakdown": asdict(cost_breakdown),
            "pricing_details": pricing_details,
        }
    
    def get_available_models(self) -> List[str]:
        """Get list of all models with pricing data."""
        return list(self.model_pricing.keys())
    
    def get_model_pricing(self, model_name: str) -> Optional[ModelPricing]:
        """Get pricing information for a specific model."""
        return self.model_pricing.get(model_name)
    
    def update_model_pricing(self, model_name: str, input_cost: float, output_cost: float) -> None:
        """Update pricing for a specific model.
        
        Args:
            model_name: Name of the model
            input_cost: Cost per 1K input tokens in USD
            output_cost: Cost per 1K output tokens in USD
        """
        average_cost = (input_cost + output_cost) / 2.0
        
        self.model_pricing[model_name] = ModelPricing(
            model_name=model_name,
            input_cost_per_1m_tokens=input_cost,
            output_cost_per_1m_tokens=output_cost,
            average_cost_per_1m_tokens=average_cost
        )
        
        if self.logger:
            self.logger.logger.info(f"Updated pricing for {model_name}: input=${input_cost:.6f}, output=${output_cost:.6f}, avg=${average_cost:.6f} per 1K tokens")
    
    def load_pricing_from_file(self, pricing_file_path: str) -> bool:
        """Load pricing data from a JSON file.
        
        Expected format:
        {
            "models": {
                "gpt-4o": {
                    "input_cost_per_1m_tokens": 0.005,
                    "output_cost_per_1m_tokens": 0.015
                },
                ...
            }
        }
        """
        try:
            if not os.path.exists(pricing_file_path):
                if self.logger:
                    self.logger.logger.warning(f"Pricing file not found: {pricing_file_path}")
                return False
            
            with open(pricing_file_path, 'r', encoding='utf-8') as f:
                pricing_data = json.load(f)
            
            
            models_data = pricing_data.get("models", {})
            for model_name, model_data in models_data.items():
                input_cost = model_data["input_cost_per_1m_tokens"]
                output_cost = model_data["output_cost_per_1m_tokens"]
                self.update_model_pricing(model_name, input_cost, output_cost)
            
            if self.logger:
                self.logger.logger.info(f"Loaded pricing for {len(models_data)} models from {pricing_file_path}")
            
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.logger.error(f"Failed to load pricing from {pricing_file_path}: {str(e)}")
            return False
    
    def save_pricing_to_file(self, pricing_file_path: str) -> bool:
        """Save current pricing data to a JSON file."""
        try:
            pricing_data = {
                "note": "Pricing in USD per 1K tokens",
                "models": {}
            }
            
            for model_name, pricing in self.model_pricing.items():
                pricing_data["models"][model_name] = {
                    "input_cost_per_1m_tokens": pricing.input_cost_per_1m_tokens,
                    "output_cost_per_1m_tokens": pricing.output_cost_per_1m_tokens,
                    "average_cost_per_1m_tokens": pricing.average_cost_per_1m_tokens
                }
            
            os.makedirs(os.path.dirname(pricing_file_path), exist_ok=True)
            
            with open(pricing_file_path, 'w', encoding='utf-8') as f:
                json.dump(pricing_data, f, indent=2, ensure_ascii=False)
            
            if self.logger:
                self.logger.logger.info(f"Saved pricing data to {pricing_file_path}")
            
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.logger.error(f"Failed to save pricing to {pricing_file_path}: {str(e)}")
            return False
    
    # ============================================================================
    # USAGE TRACKING METHODS
    # ============================================================================
    
    def record_usage(self, user_id: str, task_id: str, workflow_id: str, 
                    node_id: Optional[str], node_type: str, token_usage: Dict[str, int],
                    run_type: str = "normal") -> bool:
        """Record token usage for a specific user/task chat round.
        
        Args:
            user_id: User identifier
            task_id: Task identifier
            workflow_id: Workflow identifier  
            node_id: Node that was processed (None for flow control)
            node_type: Type of node processed
            token_usage: Token usage by model {"gpt-4o": 1500, "oai-operator": 800}
            run_type: "normal" or "checkpoint" (kept for compatibility)
        
        Returns:
            True if successfully recorded, False otherwise
        """
        try:
            # UTC+8
            timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
            total_tokens = sum(token_usage.values())
            
            # Update cumulative summary directly (no individual run tracking)
            if not self._update_usage_summary(user_id, task_id, workflow_id, token_usage, total_tokens, timestamp):
                return False
            # if self.logger:
            #     self.logger.logger.info(f"Recorded usage for user {user_id}, task {task_id}: {total_tokens} tokens")
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.logger.error(f"Failed to record usage for user {user_id}, task {task_id}: {str(e)}")
            return False
    

    
    def _update_usage_summary(self, user_id: str, task_id: str, workflow_id: str, 
                             token_usage: Dict[str, int], total_tokens: int, timestamp: str) -> bool:
        """Update cumulative usage summary for a task."""
        try:
            user_task_dir = os.path.join(self.user_usage_cache_root_dir, user_id, task_id)
            os.makedirs(user_task_dir, exist_ok=True)
            summary_path = os.path.join(user_task_dir, "usage_summary.json")
            
            # Load existing summary or create new one
            if os.path.exists(summary_path):
                with open(summary_path, 'r', encoding='utf-8') as f:
                    summary_data = json.load(f)
                    summary = UserTaskUsageSummary(**summary_data)
            else:
                summary = UserTaskUsageSummary(
                    user_id=user_id,
                    task_id=task_id,
                    workflow_id=workflow_id,
                    total_tokens=0,
                    model_breakdown={},
                    total_cost_usd=0.0,
                    chat_rounds=0,
                    created_at=timestamp,
                    updated_at=timestamp
                )
            
            # Update summary with new usage
            summary.total_tokens += total_tokens
            summary.chat_rounds += 1
            
            # Update model breakdown
            for model, tokens in token_usage.items():
                summary.model_breakdown[model] = summary.model_breakdown.get(model, 0) + tokens
            
            # Calculate updated total cost
            cost_breakdown = self.calculate_cost(summary.model_breakdown)
            summary.total_cost_usd = cost_breakdown.total_cost_usd
            
            # Update timestamp
            summary.updated_at = timestamp
            
            # Save updated summary
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(asdict(summary), f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.logger.error(f"Failed to update usage summary: {str(e)}")
            return False
    
    def get_user_task_usage(self, user_id: str, task_id: str) -> Optional[UserTaskUsageSummary]:
        """Get usage summary for a specific user/task."""
        try:
            summary_path = os.path.join(self.user_usage_cache_root_dir, user_id, task_id, "usage_summary.json")
            
            if not os.path.exists(summary_path):
                return None
            
            with open(summary_path, 'r', encoding='utf-8') as f:
                summary_data = json.load(f)
                return UserTaskUsageSummary(**summary_data)
                
        except Exception as e:
            if self.logger:
                self.logger.logger.error(f"Failed to get user task usage for {user_id}/{task_id}: {str(e)}")
            return None
    
    def get_user_tasks(self, user_id: str) -> List[str]:
        """Get list of task IDs for a user."""
        try:
            user_dir = os.path.join(self.user_usage_cache_root_dir, user_id)
            
            if not os.path.exists(user_dir):
                return []
            
            tasks = []
            for item in os.listdir(user_dir):
                task_dir = os.path.join(user_dir, item)
                if os.path.isdir(task_dir):
                    tasks.append(item)
            
            return sorted(tasks)
            
        except Exception as e:
            if self.logger:
                self.logger.logger.error(f"Failed to get user tasks for {user_id}: {str(e)}")
            return []
    
    def get_user_total_usage(self, user_id: str) -> Dict[str, Any]:
        """Get aggregated usage across all tasks for a user."""
        try:
            tasks = self.get_user_tasks(user_id)
            
            total_usage = {
                "user_id": user_id,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "model_breakdown": {},
                "task_count": len(tasks),
                "total_chat_rounds": 0,
                "tasks": []
            }
            
            for task_id in tasks:
                task_usage = self.get_user_task_usage(user_id, task_id)
                if task_usage:
                    total_usage["total_tokens"] += task_usage.total_tokens
                    total_usage["total_cost_usd"] += task_usage.total_cost_usd
                    total_usage["total_chat_rounds"] += task_usage.chat_rounds
                    
                    # Aggregate model breakdown
                    for model, tokens in task_usage.model_breakdown.items():
                        total_usage["model_breakdown"][model] = total_usage["model_breakdown"].get(model, 0) + tokens
                    
                    total_usage["tasks"].append({
                        "task_id": task_id,
                        "workflow_id": task_usage.workflow_id,
                        "tokens": task_usage.total_tokens,
                        "cost_usd": task_usage.total_cost_usd,
                        "chat_rounds": task_usage.chat_rounds,
                        "updated_at": task_usage.updated_at
                    })
            
            return total_usage
            
        except Exception as e:
            if self.logger:
                self.logger.logger.error(f"Failed to get user total usage for {user_id}: {str(e)}")
            return {"user_id": user_id, "error": str(e)}
    
    # ============================================================================
    # COMBINED USAGE + COST METHODS
    # ============================================================================
    
    def record_usage_with_cost(self, user_id: str, task_id: str, workflow_id: str, 
                              node_id: Optional[str], node_type: str, token_usage: Dict[str, int],
                              run_type: str = "normal") -> Dict[str, Any]:
        """Record usage and calculate cost in one operation.
        
        Returns:
            Dictionary with usage recording result, cost breakdown, and total task cost
        """
        result = {
            "usage_recorded": False,
            "cost_calculated": False,
            "step_cost_usd": 0.0,
            "total_task_cost_usd": 0.0,
            "error": None
        }
        
        try:
            # Record usage
            usage_success = self.record_usage(
                user_id=user_id,
                task_id=task_id, 
                workflow_id=workflow_id,
                node_id=node_id,
                node_type=node_type,
                token_usage=token_usage,
                run_type=run_type
            )
            
            result["usage_recorded"] = usage_success
            
            # Calculate cost for this chat round
            if token_usage:
                cost_breakdown = self.calculate_cost(token_usage)
                result["cost_breakdown"] = asdict(cost_breakdown)
                result["cost_calculated"] = True
                result["step_cost_usd"] = cost_breakdown.total_cost_usd
                
                # Get total task cost after this update
                task_usage = self.get_user_task_usage(user_id, task_id)
                if task_usage:
                    result["total_task_cost_usd"] = task_usage.total_cost_usd
                
                
                if self.logger:
                    self.logger.logger.info(f"Cost calculation for {user_id}/{task_id}: ${cost_breakdown.total_cost_usd:.6f} for {cost_breakdown.total_tokens} tokens, total task cost: ${result['total_task_cost_usd']:.6f}")
            
            return result
            
        except Exception as e:
            result["error"] = str(e)
            if self.logger:
                self.logger.logger.error(f"Failed to record usage with cost for {user_id}/{task_id}: {str(e)}")
            return result
    
    def get_user_task_cost_summary(self, user_id: str, task_id: str) -> Optional[Dict[str, Any]]:
        """Get cost summary for a specific user/task."""
        try:
            task_usage = self.get_user_task_usage(user_id, task_id)
            
            if not task_usage:
                return None
            
            # Cost is already calculated and stored in the summary
            return {
                "user_id": user_id,
                "task_id": task_id,
                "usage_summary": asdict(task_usage),
                "cost_per_chat_round": round(task_usage.total_cost_usd / task_usage.chat_rounds, 6) if task_usage.chat_rounds > 0 else 0.0
            }
            
        except Exception as e:
            if self.logger:
                self.logger.logger.error(f"Failed to get cost summary for {user_id}/{task_id}: {str(e)}")
            return None
    
    def get_user_total_cost_summary(self, user_id: str) -> Dict[str, Any]:
        """Get total cost summary across all tasks for a user."""
        try:
            total_usage = self.get_user_total_usage(user_id)
            
            if "error" in total_usage:
                return total_usage
            
            return {
                "user_id": user_id,
                "total_usage": total_usage,
                "average_cost_per_chat_round": round(total_usage["total_cost_usd"] / total_usage["total_chat_rounds"], 6) if total_usage["total_chat_rounds"] > 0 else 0.0,
            }
            
        except Exception as e:
            if self.logger:
                self.logger.logger.error(f"Failed to get total cost summary for {user_id}: {str(e)}")
            return {"user_id": user_id, "error": str(e)}


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_cost_estimate(token_usage: Dict[str, int], usage_tracker: Optional[UsageTracker] = None) -> Dict[str, Any]:
    """Quick utility function to get cost estimate for token usage.
    
    Args:
        token_usage: Token usage by model
        usage_tracker: Optional usage tracker (will create default if None)
    
    Returns:
        Cost estimate with breakdown
    """
    if not usage_tracker:
        # Create temporary tracker just for cost calculation
        import tempfile
        temp_dir = tempfile.mkdtemp()
        usage_tracker = UsageTracker(temp_dir)
    
    return usage_tracker.calculate_cost_with_details(token_usage)


def get_user_summary(usage_tracker: UsageTracker, user_id: str) -> Dict[str, Any]:
    """Utility function to get simplified user summary with key metrics.
    
    Args:
        usage_tracker: UsageTracker instance
        user_id: User identifier
    
    Returns:
        Dictionary with total_tokens, model_breakdown, and total_cost_usd
    """
    user_totals = usage_tracker.get_user_total_usage(user_id)
    
    if "error" in user_totals:
        return user_totals
    
    return {
        "user_id": user_id,
        "total_tokens": user_totals["total_tokens"],
        "model_breakdown": user_totals["model_breakdown"],
        "total_cost_usd": user_totals["total_cost_usd"],
        "task_count": user_totals["task_count"],
        "total_chat_rounds": user_totals["total_chat_rounds"]
    }


def aggregate_token_usage(token_usage_dict: Dict[str, int]) -> Dict[str, Any]:
    """Helper function to aggregate token usage information."""
    total_tokens = sum(token_usage_dict.values())
    
    return {
        "model_breakdown": token_usage_dict,
        "total_tokens": total_tokens,
    }
