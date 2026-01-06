from utils.gemini_client import GeminiClient
from core.graph_store import GraphStore
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class GraphBuilder:
    def __init__(self):
        """
        初始化图谱构建器
        """
        self.gemini_client = GeminiClient()
        self.graph_store = GraphStore()
        logger.info("[图谱构建器] 初始化完成")
    
    def build_graph_from_blocks(self, document_blocks: List[Dict[str, Any]], file_name: str) -> Dict[str, Any]:
        """
        从文档块构建知识图谱 (并行化)
        
        Args:
            document_blocks: 文档块列表
            file_name: 文件名
            
        Returns:
            构建结果，包含创建的实体数、关系数等
        """
        logger.info(f"[图谱构建] ========== 开始构建知识图谱，文件: {file_name} ==========")
        logger.info(f"[图谱构建] 总文档块数: {len(document_blocks)}")
        
        # 初始化统计信息
        stats = {
            "total_blocks": len(document_blocks),
            "processed_blocks": 0,
            "entities_created": 0,
            "relations_created": 0,
            "file_name": file_name
        }
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import hashlib
        
        # 准备任务
        tasks = []
        # 仅处理有内容的块
        valid_blocks = [(idx, block) for idx, block in enumerate(document_blocks) 
                       if "verified_content" in block and block["verified_content"]]
        
        logger.info(f"[图谱构建] 需处理的有效块数: {len(valid_blocks)} (总块数: {len(document_blocks)})")
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            # 提交任务
            future_to_block = {
                executor.submit(self._process_single_block, block, file_name, idx): idx 
                for idx, block in valid_blocks
            }
            
            # 处理结果
            for future in as_completed(future_to_block):
                idx = future_to_block[future]
                try:
                    result = future.result()
                    if result["processed"]:
                        stats["processed_blocks"] += 1
                        stats["entities_created"] += result["entities_count"]
                        stats["relations_created"] += result["relations_count"]
                except Exception as exc:
                    logger.error(f"[图谱构建] 块 {idx+1} 处理产生异常: {exc}")
        
        logger.info(f"[图谱构建] ========== 图谱构建完成 ==========")
        logger.info(f"[图谱构建] 处理块数: {stats['processed_blocks']}/{len(valid_blocks)}, 创建实体数: {stats['entities_created']}, 创建关系数: {stats['relations_created']}")
        
        return stats

    def _process_single_block(self, block: Dict[str, Any], file_name: str, idx: int) -> Dict[str, Any]:
        """
        处理单个文档块：提取实体关系并写入数据库
        """
        import hashlib
        
        result = {
            "processed": False,
            "entities_count": 0,
            "relations_count": 0
        }
        
        try:
            logger.info(f"[图谱构建] [Thread] 处理块 {idx+1} - 类型: {block.get('type', 'N/A')}")
            
            # 提取实体和关系 (Gemini Call - I/O Bound)
            entities_relations = self.extract_entities_relations(block["verified_content"])
            
            # 创建块节点 (DB Write)
            block_content = block["verified_content"]
            block_id = f"block_{hashlib.md5(block_content.encode('utf-8')).hexdigest()}"
            
            self.graph_store.create_block(
                block_id=block_id,
                file_name=file_name,
                page=block.get("page", 1),
                content=block_content,
                block_type=block.get("type", "unknown")
            )
            
            # 保存实体和关系 (DB Write)
            if entities_relations:
                self.graph_store.batch_create_entities_and_relations(entities_relations)
                
                # 建立实体与块的关系
                for relation in entities_relations:
                    self.graph_store.create_relation_entity_to_block(relation["source"], block_id)
                    self.graph_store.create_relation_entity_to_block(relation["target"], block_id)
                
                unique_entities = len(set([er["source"] for er in entities_relations] + [er["target"] for er in entities_relations]))
                
                result["processed"] = True
                result["entities_count"] = unique_entities
                result["relations_count"] = len(entities_relations)
                logger.info(f"[图谱构建] [Thread] 块 {idx+1} 完成 - 新增实体: {unique_entities}, 关系: {len(entities_relations)}")
            else:
                result["processed"] = True # 处理了，只是没结果
                logger.warning(f"[图谱构建] [Thread] 块 {idx+1} 未提取到实体关系")
                
        except Exception as e:
            logger.error(f"[图谱构建] [Thread] 块 {idx+1} 处理失败: {str(e)}")
            raise e
            
        return result
    
    def extract_entities_relations(self, content: str) -> List[Dict[str, Any]]:
        """
        从文本内容中提取实体和关系
        
        Args:
            content: 文本内容
            
        Returns:
            实体和关系的列表
        """
        logger.info(f"[实体提取] 开始提取实体和关系，内容长度: {len(content)} 字符")
        logger.debug(f"[实体提取] 完整输入内容: {content}")
        
        # 使用 Gemini 提取实体和关系
        entities_relations = self.gemini_client.extract_entities(content)
        logger.info(f"[实体提取] Gemini 提取到 {len(entities_relations)} 个原始实体关系")
        
        # 过滤无效的实体和关系
        filtered_results = []
        for item in entities_relations:
            # 确保源实体和目标实体都不为空
            if item["source"] and item["target"] and item["relation"]:
                filtered_results.append(item)
                logger.info(f"[实体提取] 保留有效实体关系: {item}")
            else:
                logger.warning(f"[实体提取] 过滤无效实体关系 - 源: '{item.get('source', 'None')}', 关系: '{item.get('relation', 'None')}', 目标: '{item.get('target', 'None')}'")
        
        logger.info(f"[实体提取] 过滤后保留 {len(filtered_results)} 个有效实体关系")
        logger.info(f"[实体提取] 最终有效实体关系列表: {filtered_results}")
        return filtered_results
    
    def update_graph(self, document_blocks: List[Dict[str, Any]], file_name: str) -> Dict[str, Any]:
        """
        更新知识图谱
        
        Args:
            document_blocks: 文档块列表
            file_name: 文件名
            
        Returns:
            更新结果
        """
        # 对于更新，我们先删除与该文件相关的所有实体和关系，然后重新构建
        # 注意：这里需要根据实际情况调整，可能需要更精细的更新策略
        
        # 构建图谱
        return self.build_graph_from_blocks(document_blocks, file_name)
    
    def close(self):
        """
        关闭图谱构建器，释放资源
        """
        self.graph_store.close()
    
    def get_graph_stats(self) -> Dict[str, Any]:
        """
        获取图谱统计信息
        
        Returns:
            图谱统计信息
        """
        # 获取所有实体
        all_entities = self.graph_store.get_all_entities()
        
        # 获取所有关系
        all_relations = self.graph_store.get_all_relations()
        
        # 统计关系类型
        relation_types = {}
        for relation in all_relations:
            rel_type = relation["relation"]
            relation_types[rel_type] = relation_types.get(rel_type, 0) + 1
        
        return {
            "total_entities": len(all_entities),
            "total_relations": len(all_relations),
            "relation_types": relation_types
        }
