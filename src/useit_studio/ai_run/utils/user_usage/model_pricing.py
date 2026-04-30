from dataclasses import dataclass

@dataclass
class ModelPricing:
    """Pricing information for a specific model."""
    model_name: str
    input_cost_per_1m_tokens: float  # USD per 1K input tokens
    output_cost_per_1m_tokens: float  # USD per 1K output tokens
    # For simplification, we'll use average cost since we don't separate input/output
    average_cost_per_1m_tokens: float  # USD per 1K tokens (average of input/output)


model_pricing_dict = {
    # ---------- OpenAI ----------
    "gpt-5": ModelPricing(
        model_name="gpt-5",
        input_cost_per_1m_tokens=1.25,  # $1.25 / 1M
        output_cost_per_1m_tokens=10,  # $10.00 / 1M
        average_cost_per_1m_tokens=(1.25 + 10) / 2  # $5.625 / 1M
    ),
    "gpt-5-2025-08-07": ModelPricing(
        model_name="gpt-5",
        input_cost_per_1m_tokens=1.25,  # $1.25 / 1M
        output_cost_per_1m_tokens=10, # $10.00 / 1M
        average_cost_per_1m_tokens=(1.25 + 10) / 2  # $5.625 / 1M
    ),
    "gpt-5-mini": ModelPricing(
        model_name="gpt-5-mini",
        input_cost_per_1m_tokens=0.25,  # $0.25 / 1M
        output_cost_per_1m_tokens=2.00, # $2.00 / 1M
        average_cost_per_1m_tokens=(0.25 + 2.00) / 2  # $1.125 / 1M
    ),
    "gpt-5-nano": ModelPricing(
        model_name="gpt-5-nano",
        input_cost_per_1m_tokens=0.05,  # $0.05 / 1M
        output_cost_per_1m_tokens=0.40, # $0.40 / 1M
        average_cost_per_1m_tokens=(0.05 + 0.40) / 2  # $0.225 / 1M
    ),
    "gpt-4.1": ModelPricing(
        model_name="gpt-4.1",
        input_cost_per_1m_tokens=2.00,  # $2.00 / 1M
        output_cost_per_1m_tokens=8.00, # $8.00 / 1M
        average_cost_per_1m_tokens=(2.00 + 8.00) / 2  # $5.00 / 1M
    ),
    "gpt-4.1-2025-04-14": ModelPricing(
        model_name="gpt-4.1-2025-04-14",
        input_cost_per_1m_tokens=2.00,  # $2.00 / 1M
        output_cost_per_1m_tokens=8.00, # $8.00 / 1M
        average_cost_per_1m_tokens=(2.00 + 8.00) / 2  # $5.00 / 1M
    ),
    "gpt-4o-2024-08-06": ModelPricing(
        model_name="gpt-4o-2024-08-06",
        input_cost_per_1m_tokens=2.50,  # $2.50 / 1M
        output_cost_per_1m_tokens=10.00, # $10.00 / 1M
        average_cost_per_1m_tokens=(2.50 + 10.00) / 2  # $6.25 / 1M
    ),
    # o3 after June 2025 price cut
    "o3-2025-04-16": ModelPricing(
        model_name="o3-2025-04-16",
        input_cost_per_1m_tokens=2.00,  # $2.00 / 1M
        output_cost_per_1m_tokens=8.00, # $8.00 / 1M
        average_cost_per_1m_tokens=(2.00 + 8.00) / 2  # $5.00 / 1M
    ),

    # ---------- Anthropic (Claude) ----------
    # Claude Opus 4.1 (official)
    "claude-opus-4.1": ModelPricing(
        model_name="claude-opus-4.1",
        input_cost_per_1m_tokens=15.00,  # $15.00 / 1M
        output_cost_per_1m_tokens=75.00, # $75.00 / 1M
        average_cost_per_1m_tokens=(15.00 + 75.00) / 2  # $45.00 / 1M
    ),
    # Claude Opus 4.7（API id: claude-opus-4-7）
    "claude-opus-4-7": ModelPricing(
        model_name="claude-opus-4-7",
        input_cost_per_1m_tokens=5.00,  # $5.00 / 1M
        output_cost_per_1m_tokens=25.00,  # $25.00 / 1M
        average_cost_per_1m_tokens=(5.00 + 25.00) / 2  # $15.00 / 1M
    ),
    # Claude Sonnet 4 (official; ≤200K input tokens tier)
    "claude-sonnet-4": ModelPricing(
        model_name="claude-sonnet-4",
        input_cost_per_1m_tokens=3.00,  # $3.00 / 1M
        output_cost_per_1m_tokens=15.00, # $15.00 / 1M
        average_cost_per_1m_tokens=(3.00 + 15.00) / 2  # $9.00 / 1M
    ),
    
    # ---------- Computer Use / Operator Models ----------
    "oai-operator": ModelPricing(
        model_name="oai-operator",
        input_cost_per_1m_tokens=3.00,  
        output_cost_per_1m_tokens=12.00,  
        average_cost_per_1m_tokens=(3.00 + 12.00) / 2  # $7.50 / 1M
    ),
    "computer-use-preview-2025-03-11": ModelPricing(
        model_name="computer-use-preview-2025-03-11",
        input_cost_per_1m_tokens=3.00,  
        output_cost_per_1m_tokens=12.00,  
        average_cost_per_1m_tokens=(3.00 + 12.00) / 2  # $7.50 / 1M
    ),
    "claude-computer-use": ModelPricing(
        model_name="claude-computer-use",
        input_cost_per_1m_tokens=3.00,   
        output_cost_per_1m_tokens=15.00,  
        average_cost_per_1m_tokens=(3.00 + 15.00) / 2  # $9.00 / 1M
    ),
    "claude-sonnet-4-20250514": ModelPricing(
        model_name="'claude-sonnet-4-20250514",
        input_cost_per_1m_tokens=3.00,   
        output_cost_per_1m_tokens=15.00,  
        average_cost_per_1m_tokens=(3.00 + 15.00) / 2  # $9.00 / 1M
    ),
    
    # Local run models may assign no cost
    "ui-tars": ModelPricing(
        model_name="ui-tars",
        input_cost_per_1m_tokens=0.0,   
        output_cost_per_1m_tokens=0.0,  
        average_cost_per_1m_tokens=0.0  
    ),
    
    # Default pricing for unknown models
    "unknown": ModelPricing(
        model_name="unknown",
        input_cost_per_1m_tokens=0.0,   
        output_cost_per_1m_tokens=0.0,  
        average_cost_per_1m_tokens=0.0 
    )
}