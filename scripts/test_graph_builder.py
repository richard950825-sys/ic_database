
import sys
import os
import logging
from typing import List, Dict, Any

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from agents.graph_builder import GraphBuilder
from core.config import settings

def test_adaptive_extraction():
    builder = GraphBuilder()
    
    # Mock Blocks simulating RED and YELLOW content
    mock_blocks = [
        {
            "tier": "RED",
            "verified_content": "The NLDMOS device has a specific on-resistance (Ron_sp) of 15.5 mOhm-mm2 and a breakdown voltage (BV_DSS) of 60V.",
            "type": "text",
            "page": 1
        },
        {
            "tier": "YELLOW",
            "verified_content": "Table 1: Electrical Characteristics\nRow 1: Logic Supply Voltage (Vdd) | Min: 4.5V | Max: 5.5V\nRow 2: Input High Voltage (Vih) | Min: 2.0V | Max: Vdd",
            "type": "table_text",
            "page": 2
        }
    ]
    
    file_name = "test_graph_isolation.pdf"
    
    logger.info("Starting GraphBuilder Isolation Test...")
    
    try:
        # We only want to test the extraction logic, but build_graph_from_blocks does both extraction and DB write.
        # It's cleaner to let it run and check logs, or mock the DB store. 
        # For this quick check, we'll let it write to DB (as it's dev env) or we can inspect extract_entities_relations directly.
        
        # Method 1: Direct Method Test (Cleaner, no DB side effects if we stop there)
        for block in mock_blocks:
            tier = block.get("tier")
            content = block.get("verified_content")
            logger.info(f"Testing Tier: {tier}")
            
            # This triggers the prompt formatting which caused the KeyError
            result = builder.extract_entities_relations(content, tier)
            
            logger.info(f"Result for {tier}: {result}")
            
        logger.info("Test PASSED: No KeyError raised.")
        
    except Exception as e:
        logger.error(f"Test FAILED with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_adaptive_extraction()
