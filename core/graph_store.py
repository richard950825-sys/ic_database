from neo4j import GraphDatabase
from typing import List, Dict, Any
import os
from dotenv import load_dotenv
import logging

# 加载环境变量
load_dotenv()

logger = logging.getLogger(__name__)

class GraphStore:
    def __init__(self):
        """
        初始化图数据库连接
        """
        self.driver = GraphDatabase.driver(
            uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "password"))
        )
        logger.info("[图数据库] Neo4j 连接初始化完成")
    
    def close(self):
        """
        关闭数据库连接
        """
        self.driver.close()
    
    def create_entity(self, entity_name: str, entity_type: str = "Term") -> None:
        """
        创建实体
        
        Args:
            entity_name: 实体名称
            entity_type: 实体类型（默认：Term）
        """
        with self.driver.session() as session:
            session.run(
                "MERGE (e:Entity {name: $name, type: $type})",
                name=entity_name,
                type=entity_type
            )
    
    def create_relation(self, source_entity: str, relation_type: str, target_entity: str) -> None:
        """
        创建实体之间的关系
        
        Args:
            source_entity: 源实体名称
            relation_type: 关系类型
            target_entity: 目标实体名称
        """
        with self.driver.session() as session:
            session.run(
                """
                MERGE (s:Entity {name: $source})
                MERGE (t:Entity {name: $target})
                MERGE (s)-[r:RELATION]->(t)
                SET r.type = $relation
                """,
                source=source_entity,
                target=target_entity,
                relation=relation_type
            )
            
    def create_block(self, block_id: str, file_name: str, page: int, content: str, block_type: str) -> None:
        """
        创建文档块节点
        
        Args:
            block_id: 块唯一标识
            file_name: 文件名
            page: 页码
            content: 块内容
            block_type: 块类型
        """
        with self.driver.session() as session:
            session.run(
                """
                MERGE (b:Entity {name: $block_id})
                SET b.type = 'Block',
                    b.file_name = $file_name,
                    b.page = $page,
                    b.content = $content,
                    b.block_type = $block_type
                """,
                block_id=block_id,
                file_name=file_name,
                page=page,
                content=content,
                block_type=block_type
            )
            
    def create_relation_entity_to_block(self, entity_name: str, block_id: str, relation_type: str = "MENTIONED_IN") -> None:
        """
        创建实体到文档块的关系（表明实体出自哪个块）
        
        Args:
            entity_name: 实体名称
            block_id: 文档块ID
            relation_type: 关系类型（默认：MENTIONED_IN）
        """
        with self.driver.session() as session:
            session.run(
                """
                MERGE (e:Entity {name: $entity})
                MERGE (b:Entity {name: $block_id})
                MERGE (e)-[r:RELATION]->(b)
                SET r.type = $relation
                """,
                entity=entity_name,
                block_id=block_id,
                relation=relation_type
            )
    
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def batch_create_entities_and_relations(self, entities_relations: List[Dict[str, Any]]) -> None:
        """
        批量创建实体和关系 (Optimized with UNWIND)
        
        Args:
            entities_relations: 实体和关系的列表
        """
        logger.info(f"[图数据库] ========== 开始批量创建实体和关系 (Optimized)，共 {len(entities_relations)} 个关系 ==========")
        
        # 过滤无效数据并去重，避免重复创建相同关系
        valid_items = []
        seen = set()
        
        for item in entities_relations:
            if not (item.get("source") and item.get("target") and item.get("relation")):
                continue
                
            # 创建唯一键用于去重
            key = f"{item['source']}|{item['relation']}|{item['target']}"
            if key not in seen:
                seen.add(key)
                valid_items.append({
                    "source": item["source"],
                    "target": item["target"],
                    "relation": item["relation"]
                })
        
        if not valid_items:
            logger.warning("[图数据库] 没有有效的实体关系需要创建")
            return

        logger.info(f"[图数据库] 经过去重和过滤，将处理 {len(valid_items)} 条有效关系")

        # 使用 UNWIND 语法进行批量插入
        # 注意：这里我们假设所有实体类型都是 'Term'，如果需要动态类型，需要在 valid_items 中包含类型信息
        query = """
        UNWIND $batch AS row
        MERGE (s:Entity {name: row.source})
        ON CREATE SET s.type = 'Term'
        MERGE (t:Entity {name: row.target})
        ON CREATE SET t.type = 'Term'
        MERGE (s)-[r:RELATION]->(t)
        SET r.type = row.relation
        """
        
        try:
            with self.driver.session() as session:
                session.run(query, batch=valid_items)
            logger.info(f"[图数据库] ✅ 批量插入成功: {len(valid_items)} 条关系")
        except Exception as e:
            logger.error(f"[图数据库] ❌ 批量插入失败: {str(e)}")

    
    def search_relations(self, entity_name: str, relation_type: str = None) -> List[Dict[str, Any]]:
        """
        搜索实体的关系
        
        Args:
            entity_name: 实体名称
            relation_type: 关系类型（可选）
            
        Returns:
            关系列表
        """
        with self.driver.session() as session:
            if relation_type:
                result = session.run(
                    """
                    MATCH (e:Entity)-[r:RELATION]->(t:Entity)
                    WHERE e.name = $entity
                    AND r.type = $relation
                    RETURN e.name as source, 
                           r.type as relation, 
                           t.name as target
                    """,
                    entity=entity_name,
                    relation=relation_type
                )
            else:
                result = session.run(
                    """
                    MATCH (e:Entity)-[r:RELATION]->(t:Entity)
                    WHERE e.name = $entity
                    RETURN e.name as source, 
                           r.type as relation, 
                           t.name as target
                    """,
                    entity=entity_name
                )
            
            # 处理结果
            relations = []
            for record in result:
                relations.append({
                    "source": record["source"],
                    "relation": record["relation"],
                    "target": record["target"]
                })
            
            return relations
    
    def find_shortest_path(self, source_entity: str, target_entity: str) -> List[Dict[str, Any]]:
        """
        查找两个实体之间的最短路径
        
        Args:
            source_entity: 源实体名称
            target_entity: 目标实体名称
            
        Returns:
            路径中的节点和关系
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH p=shortestPath((s:Entity)-[*..5]-(t:Entity))
                WHERE s.name = $source
                AND t.name = $target
                RETURN [n in nodes(p) | n.name] as nodes, 
                       [r in relationships(p) | {type: type(r), 
                                              source: startNode(r).name, 
                                              target: endNode(r).name}] as relations
                """,
                source=source_entity,
                target=target_entity
            )
            
            # 处理结果
            paths = []
            for record in result:
                paths.append({
                    "nodes": record["nodes"],
                    "relations": record["relations"]
                })
            
            return paths
    
    def delete_entity(self, entity_name: str) -> None:
        """
        删除实体及其所有关系
        
        Args:
            entity_name: 实体名称
        """
        with self.driver.session() as session:
            session.run(
                """
                MATCH (e:Entity {name: $name})
                DETACH DELETE e
                """,
                name=entity_name
            )
    
    def get_all_entities(self) -> List[str]:
        """
        获取所有实体
        
        Returns:
            实体名称列表
        """
        logger.debug("[图数据库] 查询所有实体")
        with self.driver.session() as session:
            result = session.run("MATCH (e:Entity) RETURN e.name as name")
            entities = [record["name"] for record in result]
            logger.debug(f"[图数据库] 查询到 {len(entities)} 个实体")
            return entities
    
    def get_all_relations(self) -> List[Dict[str, Any]]:
        """
        获取所有关系
        
        Returns:
            关系列表
        """
        logger.debug("[图数据库] 查询所有关系")
        with self.driver.session() as session:
            result = session.run(
                "MATCH (s:Entity)-[r:RELATION]->(t:Entity) RETURN s.name as source, r.type as relation, t.name as target"
            )
            relations = [
                {"source": record["source"], "relation": record["relation"], "target": record["target"]}
                for record in result
            ]
            logger.debug(f"[图数据库] 查询到 {len(relations)} 个关系")
            return relations
    
    def diagnose_entity_properties(self) -> Dict[str, Any]:
        """
        诊断数据库中实体的实际属性结构
        
        Returns:
            诊断结果，包含实体属性、关系属性等
        """
        logger.info("[图数据库] ========== 开始诊断实体属性 ==========")
        
        with self.driver.session() as session:
            # 获取第一个实体的所有属性
            result = session.run("MATCH (e:Entity) RETURN e LIMIT 1")
            entity_sample = None
            for record in result:
                entity_sample = record["e"]
                break
            
            if entity_sample:
                logger.info(f"[图数据库] 实体样本属性: {dict(entity_sample)}")
                logger.info(f"[图数据库] 实体样本属性键: {list(entity_sample.keys())}")
            else:
                logger.warning("[图数据库] 数据库中没有找到任何实体")
            
            # 获取第一个关系的所有属性
            result = session.run("MATCH (s:Entity)-[r:RELATION]->(t:Entity) RETURN r LIMIT 1")
            relation_sample = None
            for record in result:
                relation_sample = record["r"]
                break
            
            if relation_sample:
                logger.info(f"[图数据库] 关系样本属性: {dict(relation_sample)}")
                logger.info(f"[图数据库] 关系样本属性键: {list(relation_sample.keys())}")
            else:
                logger.warning("[图数据库] 数据库中没有找到任何关系")
            
            # 统计实体数量
            result = session.run("MATCH (e:Entity) RETURN count(e) as count")
            entity_count = result.single()["count"]
            logger.info(f"[图数据库] 实体总数: {entity_count}")
            
            # 统计关系数量
            result = session.run("MATCH ()-[r:RELATION]->() RETURN count(r) as count")
            relation_count = result.single()["count"]
            logger.info(f"[图数据库] 关系总数: {relation_count}")
            
            logger.info("[图数据库] ========== 诊断完成 ==========")
            
            return {
                "entity_sample": dict(entity_sample) if entity_sample else {},
                "relation_sample": dict(relation_sample) if relation_sample else {},
                "entity_count": entity_count,
                "relation_count": relation_count
            }

    def add_document(self, doc_hash: str, filename: str, size: int, upload_time: str) -> None:
        """
        添加文档元数据节点
        """
        with self.driver.session() as session:
            session.run(
                """
                MERGE (d:Document {hash: $hash})
                SET d.filename = $filename,
                    d.size = $size,
                    d.upload_time = $upload_time,
                    d.status = 'processed'
                """,
                hash=doc_hash,
                filename=filename,
                size=size,
                upload_time=upload_time
            )
            logger.info(f"[图数据库] 文档元数据已保存: {filename} (hash: {doc_hash})")

    def get_document(self, doc_hash: str) -> Dict[str, Any]:
        """
        根据哈希获取文档元数据
        """
        with self.driver.session() as session:
            result = session.run(
                "MATCH (d:Document {hash: $hash}) RETURN d",
                hash=doc_hash
            )
            record = result.single()
            if record:
                doc = dict(record["d"])
                logger.info(f"[图数据库] 找到已存在的文档: {doc.get('filename')} (hash: {doc_hash})")
                return doc
            return None

    def get_all_documents(self) -> List[Dict[str, Any]]:
        """
        获取所有已处理的文档
        """
        with self.driver.session() as session:
            result = session.run("MATCH (d:Document) RETURN d ORDER BY d.upload_time DESC")
            documents = [dict(record["d"]) for record in result]
            return documents

    def delete_document(self, filename: str) -> None:
        """
        删除文档及其关联的所有块和关系
        
        Args:
            filename: 文件名
        """
        logger.info(f"[图数据库] 开始删除文档: {filename}")
        with self.driver.session() as session:
            # 1. 删除 Document 节点
            session.run(
                "MATCH (d:Document {filename: $filename}) DETACH DELETE d",
                filename=filename
            )
            
            # 2. 删除该文档关联的 Block 节点 (以及它们的关系)
            # 注意：Entities (Terms) 通常是跨文档共享的，所以默认不删除，除非是为了彻底清理
            session.run(
                "MATCH (b:Entity {file_name: $filename}) WHERE b.type = 'Block' DETACH DELETE b",
                filename=filename
            )
            
        logger.info(f"[图数据库] 文档删除完成: {filename}")

    def clear_database(self):
        """
        清空整个图数据库
        """
        logger.warning("[图数据库] ⚠️ 正在清空整个数据库...")
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        logger.warning("[图数据库] 数据库已清空")
