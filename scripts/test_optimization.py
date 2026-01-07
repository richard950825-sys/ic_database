import time
import logging
import sys
import os
import json
import re

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.parser import PDFParser
from utils.gemini_client import GeminiClient
from core.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MockGeminiClient(GeminiClient):
    """Mock Client to track API usage without real calls."""
    def __init__(self):
        # We don't call super init to avoid google genai client init if api key missing
        self.call_count = 0
        self.total_chars_sent = 0
        self.flash_model = "mock-flash"
        self.pro_model = "mock-pro"

    def generate_text(self, prompt, use_pro=True, **kwargs):
        self.call_count += 1
        self.total_chars_sent += len(prompt)
        # logger.info(f"[MockGemini] Call #{self.call_count} (Len: {len(prompt)})")
        
        # Simulate Batch Response
        if "Block_" in prompt:
            ids = re.findall(r"Block_(\d+)", prompt)
            resp = {f"Block_{i}": f"Verified Content for Block {i}" for i in ids}
            return f"```json\n{json.dumps(resp)}\n```"
            
        return "Verified Content"

    def generate_multimodal(self, prompt, image_path=None, image_base64=None, use_pro=True):
        self.call_count += 1
        return "Image Description"

def test_pipeline(use_mock=True):
    file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test.pdf")
    
    if not os.path.exists(file_path):
        logger.error(f"File {file_path} not found.")
        return

    logger.info(f"Initializing Parser... (Mode: {'MOCK' if use_mock else 'REAL'})")
    parser = PDFParser()
    
    if use_mock:
        client = MockGeminiClient()
    else:
        client = GeminiClient()

    logger.info("="*50)
    logger.info(f"Starting processing for {file_path}")
    start_time = time.time()
    
    # 1. Parse & Chunk & Classify (Local)
    document = parser.parse_pdf(file_path)
    raw_blocks = parser.extract_document_blocks(document)
    
    logger.info(f"Extracted/Merged Blocks: {len(raw_blocks)}")
    
    # 2. Verification (API)
    verified_blocks = parser.tiered_qa_verification(raw_blocks, client)
    
    end_time = time.time()
    duration = end_time - start_time
    
    # --- Metrics ---
    logger.info("="*50)
    logger.info("OPTIMIZATION RESULTS")
    logger.info("="*50)
    logger.info(f"Total Duration:     {duration:.2f}s")
    logger.info(f"Total Final Blocks: {len(verified_blocks)}")
    logger.info(f"API Calls Made:     {client.call_count}")
    
    # Tier Stats
    tier_counts = {}
    for b in verified_blocks:
        t = b.get("tier", "Unknown")
        tier_counts[t] = tier_counts.get(t, 0) + 1
    
    logger.info(f"Tier Distribution:  {tier_counts}")
    logger.info("="*50)
    
    # Consistency Check
    red_blocks = [b for b in verified_blocks if b.get("tier") == "RED"]
    if red_blocks:
        logger.info(f"Sample RED Block: {red_blocks[0].get('content')[:100]}...")

if __name__ == "__main__":
    # Default to Mock for speed/cost safety. Change to False for real test.
    test_pipeline(use_mock=True)
