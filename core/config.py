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
    
    # Model Settings
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION_NAME", "ic_bcd_knowledge_base")

settings = Settings()
