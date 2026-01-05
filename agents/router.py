from utils.ollama_client import OllamaClient
from typing import Dict, Any

class QueryRouter:
    def __init__(self):
        """
        初始化查询路由器
        """
        self.ollama_client = OllamaClient()
    
    def route_query(self, query: str) -> Dict[str, Any]:
        """
        将用户查询路由到不同的处理流程
        
        Args:
            query: 用户查询
            
        Returns:
            路由结果，包含路由类型和路由依据
        """
        # 使用 Ollama 本地模型进行路由
        route_type = self.ollama_client.route_query(query)
        
        # 确保路由类型在预期范围内
        valid_routes = ["FACTUAL", "CONCEPTUAL", "RELATIONAL", "COMPARATIVE"]
        if route_type not in valid_routes:
            # 默认路由到 CONCEPTUAL
            route_type = "CONCEPTUAL"
        
        return {
            "route_type": route_type,
            "query": query
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
                "methods": ["exact_match", "vector_search"],
                "exact_match_params": {"limit": 3},
                "vector_search_params": {"limit": 2, "threshold": 0.85}
            },
            "CONCEPTUAL": {
                "methods": ["vector_search"],
                "vector_search_params": {"limit": 5, "threshold": 0.75}
            },
            "RELATIONAL": {
                "methods": ["graph_search"],
                "graph_search_params": {"depth": 3}
            },
            "COMPARATIVE": {
                "methods": ["vector_search", "table_extraction"],
                "vector_search_params": {"limit": 5, "filter": {"type": "table"}},
                "table_extraction_params": {"limit": 3}
            }
        }
        
        return strategies.get(route_type, strategies["CONCEPTUAL"])
