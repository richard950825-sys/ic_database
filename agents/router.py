from utils.gemini_client import GeminiClient
from typing import Dict, Any

class QueryRouter:
    def __init__(self):
        """
        初始化查询路由器
        """
        self.gemini_client = GeminiClient()
    
    def route_query(self, query: str) -> Dict[str, Any]:
        """
        将用户查询路由到不同的处理流程
        
        Args:
            query: 用户查询
            
        Returns:
            路由结果，包含路由类型和路由依据
        """
        prompt = f"""
        你是一位路由专家，负责将用户的 IC 设计和 BCD 工艺相关查询分类到正确的处理流程。
        
        请根据以下规则进行分类：
        1. "FACTUAL": 询问具体工艺参数（如数字、单位、具体数值）、规格指标
        2. "RELATIONAL": 询问跨模块影响、实体间关系、因果关系
        3. "CONCEPTUAL": 询问概念解释、原理解析、定义
        4. "COMPARATIVE": 询问比较、对比、区别
        
        用户查询：{query}
        
        请严格只输出分类标签（FACTUAL, RELATIONAL, CONCEPTUAL, COMPARATIVE 之一），不要有任何其他解释或标点符号。
        """
        
        try:
            # Use Flash model for speed
            response = self.gemini_client.generate_text(prompt, use_pro=False, temperature=0.0)
            route_type = response.strip()
        except Exception as e:
            # Fallback
            route_type = "CONCEPTUAL"

        # 确保路由类型在预期范围内
        valid_routes = ["FACTUAL", "CONCEPTUAL", "RELATIONAL", "COMPARATIVE"]
        if route_type not in valid_routes:
            route_type = "CONCEPTUAL"
        
        keywords = []
        
        # 使用 jieba 进行关键词提取
        try:
            import jieba.analyse
            # 提取 top 5 关键词, topK=5
            keywords = jieba.analyse.extract_tags(query, topK=5)
            # 如果 jieba 没提取到（例如全是停用词），回退到正则
            if not keywords:
                raise ValueError("Jieba returned empty list")
        except Exception as e:
            # 回退：简单的基于正则的分词，去除常见停用词
            import re
            ignore_words = {"的", "是", "什么", "怎么", "如何", "多少", "在", "有", "和", "与", "a", "an", "the", "what", "how"}
            # Split by non-word characters (including Chinese punctuation)
            tokens = re.split(r'[^\w]+', query.replace("?", "").replace("？", ""))
            keywords = [w for w in tokens if w not in ignore_words and len(w) > 1]
        
        return {
            "route_type": route_type,
            "query": query,
            "keywords": keywords
        }
    
    def get_retrieval_strategy(self, route_type: str) -> Dict[str, Any]:
        """
        根据路由类型获取检索策略
        
        Args:
            route_type: 路由类型
            
        Returns:
            检索策略，包含使用的检索方法、参数等
        """
        strategies = {
            "FACTUAL": {
                "methods": ["exact_match", "vector_search", "table_extraction", "image_retrieval"],
                "exact_match_params": {"limit": 3},
                "vector_search_params": {"limit": 2, "threshold": 0.85},
                "table_extraction_params": {"limit": 3},
                "image_retrieval_params": {"limit": 2}
            },
            "CONCEPTUAL": {
                "methods": ["vector_search", "image_retrieval", "table_extraction"],
                "vector_search_params": {"limit": 5, "threshold": 0.75},
                "image_retrieval_params": {"limit": 3},
                "table_extraction_params": {"limit": 3}
            },
            "RELATIONAL": {
                "methods": ["graph_search", "image_retrieval", "table_extraction"],
                "graph_search_params": {"depth": 3},
                "image_retrieval_params": {"limit": 2},
                "table_extraction_params": {"limit": 3}
            },
            "COMPARATIVE": {
                "methods": ["vector_search", "table_extraction"],
                "vector_search_params": {"limit": 10},  # Removed strict table filter, increased limit
                "table_extraction_params": {"limit": 3}
            }
        }
        
        return strategies.get(route_type, strategies["CONCEPTUAL"])
