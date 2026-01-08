from sentence_transformers import SentenceTransformer
import torch
import logging

logger = logging.getLogger(__name__)

class LocalEmbedding:
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(LocalEmbedding, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        """
        初始化本地嵌入模型 (BAAI/bge-m3) - Singleton
        """
        if self._initialized:
            logger.debug("[LocalEmbedding] Returning existing singleton instance.")
            return

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"[LocalEmbedding] Loading model {model_name} on {self.device}...")
        
        try:
            self.model = SentenceTransformer(model_name, device=self.device)
            # BGE-M3 usually produces 1024 dim dense vectors
            self._initialized = True
            logger.info(f"[LocalEmbedding] Model loaded successfully.")
        except Exception as e:
            logger.error(f"[LocalEmbedding] Failed to load model: {e}")
            raise e

    def embed(self, text: str) -> list[float]:
        """
        生成文本嵌入
        
        Args:
            text: 输入文本
            
        Returns:
            List[float]: 1024维向量
        """
        if not text:
            return []
            
        # BGE-M3 specific: It can return a dict for sparse/dense/colbert
        # But SentenceTransformer.encode default returns dense numpy array
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
