import os
from pydantic import BaseModel

class Settings(BaseModel):
    # App Settings
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    TEMP_DIR: str = "temp_uploads"
    
    # Retrieval Settings
    MAX_WORKERS: int = 5
    VECTOR_SEARCH_LIMIT: int = 5
    EXACT_MATCH_LIMIT: int = 3
    GRAPH_SEARCH_LIMIT: int = 50
    
    # Parsing Settings
    USE_OCR: bool = False
    
    # Model Settings
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION_NAME", "ic_bcd_knowledge_base")

    # Classification Prototypes & Keywords
    TIER_KEYWORDS: dict = {
        "RED": ["Breakdown Voltage", "DRC", "LDMOS", "M3", "MIM", "CMOS", "BCD", "工艺参数", "设计规则", "击穿电压", "漏电流"],
        "YELLOW": ["Table", "图", "示意图", "流程图", "参数表", "特性曲线", "Figure", "Chart"],
        "GREEN": ["摘要", "引言", "背景", "参考文献", "致谢", "Abstract", "Introduction"]
    }
    
    SEMANTIC_PROTOTYPES: dict = {
        "RED": "Process electrical parameters, breakdown voltage, leakage current constraints, device physics, semiconductor fabrication rules.",
        "YELLOW": "Detailed data tables, cross-section diagrams, schematic views, performance plots, figure captures."
    }

    # Adaptive Graph Construction Prompts
    ENTITY_EXTRACTION_PROMPTS: dict = {
        "RED": """你是一位资深的 IC/BCD 工艺参数专家。请从以下高度技术性的文本中，提取关键**工艺参数实体**及其数值属性。
文本：{text}

提取规则：
1. 目标：提取 (器件/层) -> [HAS_PARAM] -> (参数名 {{value: "...", unit: "...", condition: "..."}})
2. 标准化：务必将参数名标准化，例如 "Breakdown Voltage" -> "BV_DSS", "On-Resistance" -> "Ron_sp", "Leakage" -> "Idss"。
3. 输出格式(CSV)：
   SourceEntity, Relation, TargetEntity
   例如:
   NLDMOS, HAS_PARAM, BV_DSS {{value: "60", unit: "V"}}
   M1_Layer, RESTRICTED_BY, Width_Rule {{min: "0.5", unit: "um"}}

请只输出 CSV 行，不要其他废话。""",

        "YELLOW": """你是一位数据分析师。以下内容可能是一个转换后的表格或图表描述。请将其还原为结构化的实体关系。
文本：{text}

提取规则：
1. 每一行或每一个数据项应视为一个实体记录。
2. 提取 (Row_Entity) -> [HAS_ATTRIBUTE] -> (Value_Entity)。
3. 输出格式(CSV)：
   Source, Relation, Target
   例如:
   Device_A, HAS_RESISTANCE, 5.2_ohm
   Figure_3, SHOWS_TREND, Safe_Operating_Area

请只输出 CSV 行。""",

        "GREEN": """你是一位信息架构师。请从以下文本中提取核心概念实体。忽略过于通用的词汇。
文本：{text}

提取规则：
1. 仅提取 (概念) -> [RELATED_TO] -> (概念)。
2. 输出格式(CSV)：
   Source, Relation, Target

请只输出 CSV 行。"""
    }

settings = Settings()
