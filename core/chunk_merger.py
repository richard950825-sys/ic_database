import re
import logging
import numpy as np
from typing import List, Dict, Any
from core.embedding import LocalEmbedding

logger = logging.getLogger(__name__)

class ChunkMerger:
    def __init__(self, max_chars: int = 1000, min_chars_for_merge: int = 50, semantic_threshold: float = 0.5):
        """
        Smart/Semantic Chunk Merger for PDF blocks.
        
        Args:
            max_chars: Maximum characters per merged block.
            min_chars_for_merge: Minimum characters to consider a block "substantial" (optional logic).
            semantic_threshold: Threshold for cosine similarity (0-1). Below this, force a split.
        """
        self.max_chars = max_chars
        self.min_chars_for_merge = min_chars_for_merge
        self.semantic_threshold = semantic_threshold
        
        # Regex for detecting potential table rows
        self.table_row_pattern = re.compile(r"(\S+\s{2,}){2,}\S+")
        self.dense_number_pattern = re.compile(r".*\d.*\s+\d.*\s+\d.*")

        # Initialize Embedding Model for Semantic Checking
        # Note: Ideally this model should be shared/injected to save memory, 
        # but for now we instantiate or reuse if singleton.
        # Since LocalEmbedding loads the model, be careful about memory usage.
        # Recommendation: In production, pass the embedding model instance or use a singleton pattern.
        # Here we assume LocalEmbedding is efficient enough or used in a context where it's okay.
        # For optimization, we lazily load or assume the caller might want to check this.
        # In this specific architecture, we just instantiate it.
        try:
            self.embedding_model = LocalEmbedding()
            logger.info("[ChunkMerger] LocalEmbedding model loaded for Semantic Chunking.")
        except Exception as e:
            logger.warning(f"[ChunkMerger] Failed to load LocalEmbedding: {e}. Semantic chunking will be disabled.")
            self.embedding_model = None

    def merge_blocks(self, raw_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merge consecutive text blocks while preserving structure (tables, images) 
        and detecting potential tables. Now enhanced with Semantic Checks.
        """
        merged_blocks = []
        current_text_buffer = []
        current_buffer_len = 0
        current_page = 1
        current_coords = None 
        
        # Buffer embedding state: storing the "context" of the current buffer
        # Strategy: Use the embedding of the *last added block* to compare with the *next block*.
        # Or use average of buffer. Using last block is often better for detecting immediate shifts.
        last_block_embedding = None 

        logger.info(f"[ChunkMerger] Starting SEMANTIC merge on {len(raw_blocks)} raw blocks.")

        for i, block in enumerate(raw_blocks):
            block_type = block.get("type", "unknown")
            content = block.get("content", "")
            page = block.get("page", 1)
            
            # --- Check 1: Structural Break (Page Turn) ---
            if page != current_page:
                self._flush_buffer(merged_blocks, current_text_buffer, current_page, current_coords)
                current_text_buffer = []
                current_buffer_len = 0
                current_page = page
                current_coords = None
                last_block_embedding = None

            # --- Check 2: Non-Mergeable Types (Tables, Images) ---
            if block_type in ["table", "image", "picture"]:
                self._flush_buffer(merged_blocks, current_text_buffer, current_page, current_coords)
                current_text_buffer = []
                current_buffer_len = 0
                last_block_embedding = None
                
                # Add the non-mergeable block directly
                merged_blocks.append(block)
                continue

            # --- Check 3: Semantic Similarity (The "Smart" Split) ---
            # Only check if we have a buffer, the new block has text, and we have a model
            should_semantically_split = False
            if self.embedding_model and current_text_buffer and len(content) > 20:
                # If current buffer matches table row pattern, and new one doesn't (or vice versa), maybe split?
                # Rely on embedding for now.
                
                # Compute embedding for new content
                try:
                    current_embedding = self.embedding_model.embed(content)
                    if hasattr(current_embedding, 'tolist'): 
                        current_embedding = current_embedding.tolist()
                    
                    if last_block_embedding:
                        sim = self._cosine_similarity(last_block_embedding, current_embedding)
                        # debug logging for tuning
                        # logger.debug(f"[ChunkMerger] Sim: {sim:.3f} | Buffer: {current_text_buffer[-1][:20]}... | Next: {content[:20]}...")
                        
                        if sim < self.semantic_threshold:
                            should_semantically_split = True
                            logger.info(f"[ChunkMerger] Semantic Split Triggered (Sim: {sim:.2f})")
                    
                    # Update state
                    last_block_embedding = current_embedding
                    
                except Exception as e:
                    logger.warning(f"[ChunkMerger] Semantic check failed: {e}")

            if should_semantically_split:
                 self._flush_buffer(merged_blocks, current_text_buffer, current_page, current_coords)
                 current_text_buffer = []
                 current_buffer_len = 0
                 current_coords = None
                 # last_block_embedding is already updated to the NEW block's embedding above

            # --- Check 4: Size Limit ---
            if current_buffer_len + len(content) > self.max_chars:
                self._flush_buffer(merged_blocks, current_text_buffer, current_page, current_coords)
                current_text_buffer = []
                current_buffer_len = 0
                current_coords = None
                # Reset embedding context after size flush? 
                # Yes, because the physical block is full. The next block starts a new physical chunk.
                # However, for semantic comparison, the "last block" is still relevant if we wanted to
                # keep continuity, but here we must split.
                # last_block_embedding remains current block's embedding (calculated above if checks passed)
                # If we didn't calc embedding above (e.g. checks skipped), we might need it now?
                # Simplification: If we flushed due to size, just carry on.

            # --- Add to Buffer ---
            if not current_text_buffer:
                current_coords = block.get("coordinates")
            
            # If we missed calculating embedding (e.g. len < 20 or first block)
            if self.embedding_model and last_block_embedding is None and len(content) > 5:
                 try:
                    last_block_embedding = self.embedding_model.embed(content)
                    if hasattr(last_block_embedding, 'tolist'):
                        last_block_embedding = last_block_embedding.tolist()
                 except: pass

            current_text_buffer.append(content)
            current_buffer_len += len(content) + 1 

        # Flush remaining
        self._flush_buffer(merged_blocks, current_text_buffer, current_page, current_coords)
        
        logger.info(f"[ChunkMerger] Merged into {len(merged_blocks)} blocks (Reduction: {100 * (1 - len(merged_blocks)/len(raw_blocks) if len(raw_blocks) else 0):.1f}%)")
        return merged_blocks

    def _flush_buffer(self, merged_blocks, buffer, page, coords):
        if not buffer:
            return
            
        full_text = "\n".join(buffer)
        
        # Heuristic Table Classification
        tier = "GREEN" 
        block_type = "text"
        
        if self._is_potential_table_chunk(full_text):
            tier = "YELLOW"
            block_type = "potential_table"
            logger.info(f"[ChunkMerger] Detected Potential Table: {full_text[:50]}...")

        merged_block = {
            "type": block_type,
            "page": page,
            "content": full_text,
            "tier": tier, 
            "coordinates": coords
        }
        merged_blocks.append(merged_block)

    def _cosine_similarity(self, vec1, vec2):
        if not vec1 or not vec2: return 0.0
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0: return 0.0
        return np.dot(v1, v2) / (norm1 * norm2)

    def _is_potential_table_row(self, text: str) -> bool:
        """Check if a single line looks like a table row."""
        if len(text) < 5: return False
        return bool(self.table_row_pattern.search(text) or self.dense_number_pattern.search(text))

    def _is_potential_table_chunk(self, text: str) -> bool:
        """Check if the merged chunk looks like a table."""
        lines = text.split('\n')
        if not lines: return False
        
        table_like_lines = sum(1 for line in lines if self._is_potential_table_row(line))
        
        if len(lines) > 2 and (table_like_lines / len(lines) > 0.4):
            return True
        return False
