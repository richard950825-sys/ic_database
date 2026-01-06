from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, CollectionDescription, VectorParams, TextIndexParams, TokenizerType
from typing import List, Dict, Any
from utils.gemini_client import GeminiClient
import os
from dotenv import load_dotenv
import logging
import uuid

# 加载环境变量
load_dotenv()

logger = logging.getLogger(__name__)

class VectorStore:
    def __init__(self):
        """
        初始化向量存储
        """
        if hasattr(self, "_initialized") and self._initialized:
            return
        
        # 连接到 Qdrant 服务
        self.client = QdrantClient(
            url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            api_key=os.getenv("QDRANT_API_KEY")
        )
        
        # 初始化 Gemini 客户端用于生成嵌入
        self.gemini_client = GeminiClient()
        
        # 定义集合名称
        self.collection_name = os.getenv("QDRANT_COLLECTION_NAME", "ic_bcd_knowledge_base")
        
        # 检查集合是否存在，不存在则创建
        self._ensure_collection_exists()
        
        self._initialized = True
        logger.info(f"[向量库] Qdrant 向量库初始化完成，集合: {self.collection_name} (Using Gemini Embeddings)")
    
    def _ensure_collection_exists(self):
        """
        确保集合存在，不存在则创建
        """
        # 获取所有集合
        collections = self.client.get_collections().collections
        collection_names = [col.name for col in collections]
        
        # 如果集合不存在，则创建
        if self.collection_name not in collection_names:
            logger.info(f"[向量库] 创建新集合: {self.collection_name}")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=int(os.getenv("GEMINI_EMBEDDING_DIMENSION", 768)),  # Gemini text-embedding-004 dimension
                    distance="Cosine"
                )
            )
        else:
            # Check existing collection dimension
            target_dim = int(os.getenv("GEMINI_EMBEDDING_DIMENSION", 768))
            info = self.client.get_collection(self.collection_name)
            if info.config.params.vectors.size != target_dim:
                logger.warning(f"[向量库] 现有集合维度 ({info.config.params.vectors.size}) 与 Gemini ({target_dim}) 不匹配。重建集合...")
                self.client.delete_collection(self.collection_name)
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=target_dim,
                        distance="Cosine"
                    )
                )
            
            # 创建全文索引
            logger.info("[向量库] 为 content 字段创建全文索引")
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="content",
                field_schema=TextIndexParams(
                    type="text",
                    tokenizer=TokenizerType.WORD,
                    min_token_len=2,
                    max_token_len=15,
                    lowercase=True
                )
            )
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        生成文本的嵌入向量
        
        Args:
            text: 要生成嵌入的文本
            
        Returns:
            嵌入向量
        """
        return self.gemini_client.generate_embedding(text)
    
    def add_document_block(self, block: Dict[str, Any], file_name: str) -> str:
        """
        添加文档块到向量存储
        
        Args:
            block: 文档块
            file_name: 文件名
            
        Returns:
            添加的点的 ID
        """
        # 准备要嵌入的文本
        if block["type"] == "text" or block["type"] == "table":
            # 文本或表格，使用验证后的内容
            text_to_embed = block["verified_content"]
        elif block["type"] == "image":
            # 图像，使用生成的描述
            text_to_embed = block["verified_content"]
        else:
            text_to_embed = str(block["content"])
        
        logger.debug(f"[向量库] 准备添加文档块 - 文件: {file_name}, 类型: {block['type']}, 页码: {block['page']}, 内容长度: {len(text_to_embed)}")
        
        # 生成嵌入向量
        embedding = self.generate_embedding(text_to_embed)
        logger.debug(f"[向量库] 嵌入向量生成完成，维度: {len(embedding)}")
        
        # 准备元数据
        metadata = {
            "file_name": file_name,
            "type": block["type"],
            "page": block["page"],
            "tier": block["tier"],
            "coordinates": block["coordinates"],
            "content": text_to_embed
        }
        
        # 如果是图像，添加图像的 Base64 编码
        if block["type"] == "image":
            metadata["image_base64"] = block["content"]
        
        # 生成点 ID - 使用 UUID 格式
        point_id = str(uuid.uuid4())
        
        # 添加点到集合
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=metadata
                )
            ]
        )
        
        logger.debug(f"[向量库] 文档块添加成功 - ID: {point_id}")
        return point_id
    
    def search_similar(self, query: str, limit: int = 5, filter_criteria: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        搜索相似的文档块
        
        Args:
            query: 查询文本
            limit: 返回结果的数量
            filter_criteria: 过滤条件
            
        Returns:
            相似的文档块列表
        """
        logger.debug(f"[向量库] 开始相似性搜索 - 查询: {query}, 限制: {limit}")
        
        # 生成查询的嵌入向量
        query_embedding = self.generate_embedding(query)
        
        # 执行搜索
        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            limit=limit,
            query_filter=filter_criteria
        ).points
        
        # 处理搜索结果
        search_results = []
        for result in results:
            search_results.append({
                "score": result.score,
                "metadata": result.payload,
                "id": result.id
            })
            logger.info(f"[向量库] 搜索结果 - ID: {result.id}, 分数: {result.score}")
            if hasattr(result, 'payload') and result.payload:
                content = result.payload.get('content', result.payload.get('verified_content', ''))
                logger.info(f"[向量库] 搜索结果内容 - 文件: {result.payload.get('file_name', 'N/A')}, 页码: {result.payload.get('page', 'N/A')}")
                logger.info(f"[向量库] 搜索结果内容预览: {content[:200]}...")
        
        logger.info(f"[向量库] 搜索完成，返回 {len(search_results)} 个结果")
        return search_results
    
    def exact_match_search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        精确匹配搜索
        
        Args:
            query: 查询文本
            limit: 返回结果的数量
            
        Returns:
            匹配的文档块列表
        """
        # 使用 Qdrant 的关键字过滤功能
        # 注意：这是一个简单的实现，实际应用中可能需要更复杂的 BM25 实现
        results = self.client.query_points(
            collection_name=self.collection_name,
            query=self.generate_embedding(query),
            limit=limit,
            query_filter={
                "must": [
                    {
                        "key": "content",
                        "match": {
                            "text": query
                        }
                    }
                ]
            }
        ).points
        
        # 处理搜索结果
        search_results = []
        for result in results:
            search_results.append({
                "score": result.score,
                "metadata": result.payload,
                "id": result.id
            })
        
        return search_results

    def search_tables(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        专门搜索表格内容
        
        Args:
            query: 查询文本
            limit: 返回结果的数量
        """
        from qdrant_client import models
        logger.info(f"[向量库] 执行表格专项搜索 - 查询: {query}")
        
        return self.search_similar(
            query,
            limit=limit,
            filter_criteria=models.Filter(
                must=[
                    models.FieldCondition(
                        key="type",
                        match=models.MatchValue(value="table")
                    )
                ]
            )
            )


    def search_images(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        专门搜索图像内容
        
        Args:
            query: 查询文本
            limit: 返回结果的数量
        """
        from qdrant_client import models
        logger.info(f"[向量库] 执行图像专项搜索 - 查询: {query}")
        
        return self.search_similar(
            query,
            limit=limit,
            filter_criteria=models.Filter(
                must=[
                    models.FieldCondition(
                        key="type",
                        match=models.MatchValue(value="image")
                    )
                ]
            )
        )
    
    def delete_by_file_name(self, file_name: str):
        """
        根据文件名删除文档块
        
        Args:
            file_name: 文件名
        """
        from qdrant_client import models
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="file_name",
                            match=models.MatchValue(value=file_name)
                        )
                    ]
                )
            )
        )
    
    def get_collection_info(self):
        """
        获取集合信息
        
        Returns:
            集合信息
        """
        logger.debug("[向量库] 获取集合信息")
        try:
            collection_info = self.client.get_collection(collection_name=self.collection_name)
            
            # 检查CollectionInfo对象的属性
            logger.debug(f"[向量库] CollectionInfo对象属性: {[attr for attr in dir(collection_info) if not attr.startswith('_')]}")
            
            # 提取可用的集合信息
            info = {
                "collection_name": self.collection_name,
                "vectors_count": getattr(collection_info, 'vectors_count', 'N/A'),
                "points_count": getattr(collection_info, 'points_count', 'N/A')
            }
            
            logger.debug(f"[向量库] 集合信息 - 名称: {info['collection_name']}, 向量数: {info['vectors_count']}, 点数: {info['points_count']}")
            return info
        except Exception as e:
            logger.error(f"[向量库] 获取集合信息失败: {str(e)}")
            return {
                "error": str(e)
            }

    def clear_collection(self):
        """
        清空向量集合 (删除并重建)
        """
        logger.warning(f"[向量库] ⚠️ 正在清空集合: {self.collection_name}")
        try:
            self.client.delete_collection(self.collection_name)
            # Re-create immediately
            self._ensure_collection_exists()
            logger.warning("[向量库] 集合已清空并重建")
        except Exception as e:
            logger.error(f"[向量库] 清空集合失败: {e}")
