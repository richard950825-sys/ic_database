from sentence_transformers import SentenceTransformer
import torch
import logging

logger = logging.getLogger(__name__)

class LocalEmbedding:
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        """
        初始化本地嵌入模型 (BAAI/bge-m3)
        """
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"[LocalEmbedding] Loading model {model_name} on {self.device}...")
        
        try:
            self.model = SentenceTransformer(model_name, device=self.device)
            # BGE-M3 usually produces 1024 dim dense vectors
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
