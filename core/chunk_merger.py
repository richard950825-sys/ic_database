import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ChunkMerger:
    def __init__(self, max_chars: int = 1000, min_chars_for_merge: int = 50):
        """
        Smart Chunk Merger for PDF blocks.
        
        Args:
            max_chars: Maximum characters per merged block.
            min_chars_for_merge: Minimum characters to consider a block "substantial" (optional logic).
        """
        self.max_chars = max_chars
        self.min_chars_for_merge = min_chars_for_merge
        
        # Regex for detecting potential table rows (e.g., multiple numbers separated by spaces/tabs)
        # Matches lines like: "1.2  3.4  5.6" or "Parameter  Value  Unit"
        self.table_row_pattern = re.compile(r"(\S+\s{2,}){2,}\S+")
        self.dense_number_pattern = re.compile(r".*\d.*\s+\d.*\s+\d.*")

    def merge_blocks(self, raw_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merge consecutive text blocks while preserving structure (tables, images) 
        and detecting potential tables.
        """
        merged_blocks = []
        current_text_buffer = []
        current_buffer_len = 0
        current_page = 1
        current_coords = None # Store bounding box of merged block (simplification: use first block's start, last block's end)
        
        logger.info(f"[ChunkMerger] Starting merge on {len(raw_blocks)} raw blocks.")

        for block in raw_blocks:
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

            # --- Check 2: Non-Mergeable Types (Tables, Images) ---
            if block_type in ["table", "image", "picture"]:
                # Flush existing buffer first
                self._flush_buffer(merged_blocks, current_text_buffer, current_page, current_coords)
                current_text_buffer = []
                current_buffer_len = 0
                
                # Add the non-mergeable block directly
                merged_blocks.append(block)
                continue

            # --- Check 3: Heuristic Table Detection ---
            # If a text block looks like a table row, verify if it should separate or merge
            # For now, if we detect a table row, we might want to treat it as a "potential table"
            # But simplistic merging might actually HELP table reconstruction if we merge rows.
            # However, if we merge headers with table rows, confusion arises.
            # Strategy: If the block looks like a table row:
            # 1. If we are already buffering text, inspect the buffer. If header-like, maybe merge.
            # 2. But ideally, we mark this block.
            
            # Current simplified strategy:
            # - Merge text normally.
            # - Post-process validation or during flush check if the merged block looks like a table.
            
            # Let's perform detection on the *content* being added.
            is_potential_table_row = self._is_potential_table_row(content)
            
            # Optional: If we hit a table-row-like line, and the buffer is huge, flush it to keep context separate?
            # Or just keep merging to form a "Text Table".
            # Decision: Keep merging. We will classify the *result* later.
            
            # --- Check 4: Size Limit ---
            if current_buffer_len + len(content) > self.max_chars:
                self._flush_buffer(merged_blocks, current_text_buffer, current_page, current_coords)
                current_text_buffer = []
                current_buffer_len = 0
                current_coords = None

            # --- Add to Buffer ---
            if not current_text_buffer:
                # Capture start coords (approximate)
                current_coords = block.get("coordinates")
            
            current_text_buffer.append(content)
            current_buffer_len += len(content) + 1 # +1 for newline/space

        # Flush remaining
        self._flush_buffer(merged_blocks, current_text_buffer, current_page, current_coords)
        
        logger.info(f"[ChunkMerger] Merged into {len(merged_blocks)} blocks (Reduction: {100 * (1 - len(merged_blocks)/len(raw_blocks) if len(raw_blocks) else 0):.1f}%)")
        return merged_blocks

    def _flush_buffer(self, merged_blocks, buffer, page, coords):
        if not buffer:
            return
            
        full_text = "\n".join(buffer)
        
        # Heuristic Table Classification on the merged chunk
        tier = "GREEN" # Default
        block_type = "text"
        
        # If the text is dense with numbers or aligned looking, flag it
        if self._is_potential_table_chunk(full_text):
            tier = "YELLOW" # Upgrade to YELLOW for LLM verification
            block_type = "potential_table"
            logger.debug(f"[ChunkMerger] Detected Potential Table: {full_text[:50]}...")

        merged_block = {
            "type": block_type,
            "page": page,
            "content": full_text,
            "tier": tier, # Pre-calculate heuristic tier, will be overridden by semantic classifier if stronger
            "coordinates": coords
        }
        merged_blocks.append(merged_block)

    def _is_potential_table_row(self, text: str) -> bool:
        """Check if a single line looks like a table row."""
        if len(text) < 5: return False
        return bool(self.table_row_pattern.search(text) or self.dense_number_pattern.search(text))

    def _is_potential_table_chunk(self, text: str) -> bool:
        """Check if the merged chunk looks like a table."""
        # Count lines that look like rows
        lines = text.split('\n')
        if not lines: return False
        
        table_like_lines = sum(1 for line in lines if self._is_potential_table_row(line))
        
        # If > 50% of lines look like table rows, or if we have > 3 table-like lines consecutively
        if len(lines) > 2 and (table_like_lines / len(lines) > 0.4):
            return True
        return False
