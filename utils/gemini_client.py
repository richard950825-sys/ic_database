import google.genai as genai
from dotenv import load_dotenv
import os
import base64
from PIL import Image
import io
import logging
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log
import sys

# Force UTF-8 encoding for Windows (fixes UnicodeEncodeError in logging)
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

load_dotenv()

class GeminiClient:
    def __init__(self):
        """
        初始化 Gemini 客户端
        """
        # 获取代理配置
        http_proxy = os.getenv("HTTP_PROXY")
        https_proxy = os.getenv("HTTPS_PROXY")
        
        # 设置全局代理环境变量
        if http_proxy:
            os.environ["HTTP_PROXY"] = http_proxy
            os.environ["http_proxy"] = http_proxy
        if https_proxy:
            os.environ["HTTPS_PROXY"] = https_proxy
            os.environ["https_proxy"] = https_proxy
        
        # 初始化客户端
        self.client = genai.Client(
            api_key=os.getenv("GOOGLE_API_KEY")
        )
        
        self.pro_model = os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-pro")
        self.flash_model = os.getenv("GEMINI_FLASH_MODEL_NAME", "gemini-1.5-flash")
        
        # 记录代理配置
        proxy_url = http_proxy or https_proxy
        if proxy_url:
            logging.info(f"[GeminiClient] 使用代理: {proxy_url}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
        before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING)
    )
    def generate_text(self, prompt: str, use_pro: bool = False, **kwargs) -> str:
        """
        生成文本内容
        """
        model = self.pro_model if use_pro else self.flash_model
        try:
            response = self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=kwargs
            )
            if hasattr(response, 'text') and response.text:
                return response.text
            else:
                logging.warning(f"[GeminiClient] 生成内容为空 or 被拦截。Response: {response}")
                return ""
        except Exception as e:
            logging.error(f"[GeminiClient] 生成失败: {e}")
            return ""
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
        before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING)
    )
    def generate_multimodal(self, prompt: str, image_path: str = None, image_base64: str = None, use_pro: bool = True) -> str:
        """
        生成多模态内容
        """
        model = self.pro_model if use_pro else self.flash_model
        
        contents = [prompt]
        
        if image_path:
            image = Image.open(image_path)
        elif image_base64:
            image_data = base64.b64decode(image_base64)
            image = Image.open(io.BytesIO(image_data))
        else:
            raise ValueError("必须提供 image_path 或 image_base64")
        
        contents.append(image)
        
        try:
            response = self.client.models.generate_content(
                model=model,
                contents=contents
            )
            if hasattr(response, 'text') and response.text:
                return response.text
            else:
                logging.warning(f"[GeminiClient] 多模态生成内容为空 or 被拦截。Response: {response}")
                return ""
        except Exception as e:
            logging.error(f"[GeminiClient] 多模态生成失败: {e}")
            return ""
    
    def generate_embedding(self, text: str) -> list:
        """
        [DEPRECATED] 生成文本嵌入
        Now using Local BGE-M3 model in core/embedding.py
        """
        raise NotImplementedError("Gemini embedding is deprecated. Use LocalEmbedding instead.")

    
    def extract_entities(self, text: str) -> list:
        """
        从文本中提取实体和关系
        """
        logger = logging.getLogger(__name__)
        logger.info(f"[LLM实体提取] 开始提取实体和关系 - 文本长度: {len(text)} 字符")
        logger.debug(f"[LLM实体提取] 输入文本: {text}")
        
        prompt = f"""你是一位资深的 IC 设计和 BCD 工艺专家。请从以下文本中提取实体和它们之间的关系：

文本：{text}

请按照以下格式输出：
实体1,关系,实体2
实体1,关系,实体3
...

关系类型包括：Defined_in, Restricted_by, Has_property, Connected_to, Used_in, etc.

请只输出提取的内容，不要添加任何其他解释。"""
        
        logger.debug(f"[LLM实体提取] 生成的提示词: {prompt}")
        response = self.generate_text(prompt, use_pro=True)
        logger.info(f"[LLM实体提取] LLM返回结果长度: {len(response)} 字符")
        logger.debug(f"[LLM实体提取] LLM原始返回: {response}")
        
        entities = []
        lines = response.strip().split("\n")
        logger.info(f"[LLM实体提取] LLM返回行数: {len(lines)}")
        
        for line in lines:
            line = line.strip()
            if line:
                parts = line.split(",")
                logger.debug(f"[LLM实体提取] 处理行: {line} -> 分割为 {len(parts)} 部分: {parts}")
                if len(parts) == 3:
                    entity_relation = {
                        "source": parts[0].strip(),
                        "relation": parts[1].strip(),
                        "target": parts[2].strip()
                    }
                    entities.append(entity_relation)
                    logger.info(f"[LLM实体提取] 成功解析实体关系: {entity_relation}")
                else:
                    logger.warning(f"[LLM实体提取] 无效的实体关系行: {line}")
        
        logger.info(f"[LLM实体提取] 提取完成 - 共提取到 {len(entities)} 个实体关系")
        logger.debug(f"[LLM实体提取] 最终实体关系列表: {entities}")
        return entities
