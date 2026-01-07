import os
import shutil
import logging
import uuid
from typing import List, Optional
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.parser import PDFParser
from core.vector_store import VectorStore
from core.graph_store import GraphStore
from agents.graph_builder import GraphBuilder
from utils.gemini_client import GeminiClient
from agents.router import QueryRouter
from agents.analyzer import DomainAnalyzer
from agents.auditor import ResponseAuditor
from graph_flow import run_workflow
from core.config import settings

# Load env vars
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("server.log", encoding='utf-8')
    ]
)
logger = logging.getLogger("server")

# Suppress noisy logs
logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

# Filter out repetitive polling logs from uvicorn
class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/api/task/" not in record.getMessage()

logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

# Lifespan manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing system components...")
    
    # Store components in app.state
    # Initialize Global Executor
    app.state.executor = ThreadPoolExecutor(max_workers=settings.MAX_WORKERS)
    
    # Initialize Core Components
    app.state.parser = PDFParser()
    app.state.vector_store = VectorStore()
    app.state.graph_store = GraphStore()
    app.state.graph_builder = GraphBuilder()
    app.state.gemini_client = GeminiClient()
    
    # Initialize Logic Agents
    app.state.router = QueryRouter()
    app.state.domain_analyzer = DomainAnalyzer()
    app.state.auditor = ResponseAuditor()
    
    # Components Dictionary for Injection
    app.state.components = {
        "router": app.state.router,
        "vector_store": app.state.vector_store,
        "graph_store": app.state.graph_store,
        "domain_analyzer": app.state.domain_analyzer,
        "auditor": app.state.auditor,
        "gemini_client": app.state.gemini_client,
        "executor": app.state.executor  # Shared Executor
    }
    
    logger.info("System components initialized successfully.")
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    app.state.executor.shutdown(wait=True)

app = FastAPI(lifespan=lifespan)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Types
class ChatRequest(BaseModel):
    query: str

class ChatResponse(BaseModel):
    answer: str
    sources: List[dict]
    audit_passed: bool
    revision_count: int

# Task Manager
class TaskManager:
    def __init__(self):
        self.tasks = {}
    
    def create_task(self):
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "status": "pending",
            "progress": 0,
            "message": "等待开始...",
            "details": "",
            "is_cancelled": False
        }
        return task_id

    def update_task(self, task_id, status, progress, message, details=""):
        if task_id in self.tasks:
             # Prevent overwriting if already cancelled
            if self.tasks[task_id].get("is_cancelled"):
                return
            self.tasks[task_id].update({
                "status": status,
                "progress": progress, 
                "message": message,
                "details": details
            })

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def cancel_task(self, task_id):
        if task_id in self.tasks:
            self.tasks[task_id]["is_cancelled"] = True
            self.tasks[task_id]["status"] = "cancelled"
            self.tasks[task_id]["message"] = "已取消"
            logger.info(f"Task {task_id} marked for cancellation")

task_manager = TaskManager()

# Routes
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return JSONResponse(content={})

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Background Processing
def process_file_background(task_id: str, file_path: str, filename: str, app_state):
    try:
        if task_manager.get_task(task_id).get("is_cancelled"): return

        task_manager.update_task(task_id, "processing", 10, "解析 PDF...", "开始解析文档结构")
        
        def parse_callback(current, total, msg=""):
            if task_manager.get_task(task_id).get("is_cancelled"): raise Exception("Task Cancelled")
            p = 10 + int((current / total) * 40) if total > 0 else 10
            task_manager.update_task(task_id, "processing", p, "QA 验证与解析中...", f"{msg} ({current}/{total})")

        def graph_callback(current, total, msg=""):
            if task_manager.get_task(task_id).get("is_cancelled"): raise Exception("Task Cancelled")
            p = 50 + int((current / total) * 40) if total > 0 else 50
            task_manager.update_task(task_id, "processing", p, "构建知识图谱中...", f"{msg} ({current}/{total})")

        parser = app_state.parser
        vector_store = app_state.vector_store
        graph_builder = app_state.graph_builder
        graph_store = app_state.graph_store
        gemini_client = app_state.gemini_client

        # 1. Parse
        # Using simulated callback support via wrapper or direct call if supported
        # We assume parser supports progress_callback as per previous edits
        docs = parser.process_pdf(file_path, gemini_client, progress_callback=parse_callback)
        
        if task_manager.get_task(task_id).get("is_cancelled"): return

        logger.info(f"Parsed {len(docs)} documents/chunks")
        task_manager.update_task(task_id, "processing", 50, "写入向量库...", f"共 {len(docs)} 个块")
        
        # 2. Add to Vector Store
        vector_store.add_documents(docs, file_name=filename)
        
        if task_manager.get_task(task_id).get("is_cancelled"): return

        # 3. Build Graph
        graph_builder.build_graph_from_blocks(docs, file_name=filename, progress_callback=graph_callback)

        # 4. Save metadata
        import hashlib
        import time
        file_hash = hashlib.md5(filename.encode()).hexdigest()
        file_size = os.path.getsize(file_path)
        graph_store.add_document(file_hash, filename, file_size, time.strftime("%Y-%m-%d %H:%M:%S"))

        task_manager.update_task(task_id, "completed", 100, "处理完成", "所有步骤已完成")

    except Exception as e:
        if str(e) == "Task Cancelled":
            task_manager.update_task(task_id, "cancelled", 0, "已取消", "用户取消上传")
            logger.warning(f"Task {task_id} cancelled. Cleaning up resources for file: {filename}")
            
            # Clean up Database
            try:
                # 1. Vector Store
                vector_store.delete_document(filename)
                logger.info(f"Cleaned up Vector Store for {filename}")
                
                # 2. Graph Store
                graph_store.delete_document(filename)
                logger.info(f"Cleaned up Graph Store for {filename}")
                
            except Exception as cleanup_error:
                logger.error(f"Error during cleanup for cancelled task {task_id}: {cleanup_error}")
                
        else:
            logger.error(f"Error processing file: {e}")
            import traceback
            traceback.print_exc()
            task_manager.update_task(task_id, "error", 0, "处理失败", str(e))
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass

@app.post("/api/upload")
async def upload_files(request: Request, files: List[UploadFile] = File(...), background_tasks: BackgroundTasks = None):
    results = []
    
    # Check dependencies
    if not hasattr(request.app.state, 'parser'):
        raise HTTPException(status_code=503, detail="System initializing...")

    os.makedirs(settings.TEMP_DIR, exist_ok=True)

    for file in files:
        if not file.filename.endswith('.pdf'):
            continue
            
        task_id = task_manager.create_task()
        
        # SECURITY FIX: Path Traversal
        safe_filename = os.path.basename(file.filename)
        # Add basic check
        if ".." in safe_filename or "/" in safe_filename or "\\" in safe_filename:
             task_manager.update_task(task_id, "error", 0, "非法文件名", "Filename blocked for security")
             continue

        file_path = os.path.join(settings.TEMP_DIR, f"{task_id}_{safe_filename}")
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        background_tasks.add_task(process_file_background, task_id, file_path, safe_filename, request.app.state)
        
        results.append({"filename": safe_filename, "task_id": task_id})

    return results

@app.get("/api/task/{task_id}")
async def get_task_status(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.post("/api/task/{task_id}/cancel")
async def cancel_task(task_id: str):
    task_manager.cancel_task(task_id)
    return {"status": "cancelling"}

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    try:
        logger.info(f"Received chat query: {body.query}")
        result = run_workflow(body.query, components=request.app.state.components)
        
        # Flatten sources for frontend
        flat_sources = []
        for ctx in result["retrieved_contexts"]:
            metadata = ctx.get("metadata", {})
            flat_sources.append({
                "file_name": metadata.get("file_name", "Unknown"),
                "page": metadata.get("page", 1),
                "score": ctx.get("score", 0),
                "type": metadata.get("type", "text"),
                "content": metadata.get("content", "")
            })

        return ChatResponse(
            answer=result["generated_answer"],
            sources=flat_sources,
            audit_passed=result["audit_passed"],
            revision_count=result["revision_count"]
        )
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/files")
async def list_files(request: Request):
    try:
        # User reported 'null' filenames.
        # Root cause: add_document sets 'filename', but this query was reading 'name'.
        query = "MATCH (d:Document) RETURN DISTINCT d.filename as filename, d.upload_time as time, d.size as size"
        results = request.app.state.graph_store.query(query)
        
        files = []
        for r in results:
            files.append({
                "filename": r.get("filename"),
                "upload_time": r.get("time"),
                "size": r.get("size")
            })
        return JSONResponse(content=files)
    except Exception as e:
        logger.warning(f"Could not list files from Graph: {e}")
        return JSONResponse(content=[])

@app.delete("/api/files/{filename}")
async def delete_file(request: Request, filename: str):
    try:
        # SECURITY FIX: Path Traversal
        safe_filename = os.path.basename(filename)
        if safe_filename != filename:
             raise HTTPException(status_code=400, detail="Invalid filename format")

        # 1. Delete from Vector Store
        if hasattr(request.app.state.vector_store, 'delete_by_file_name'):
            request.app.state.vector_store.delete_by_file_name(safe_filename)
        else:
            logger.warning("VectorStore missing delete_by_file_name method")

        # 2. Delete from Graph Store
        # Use the dedicated method which handles property names correctly (filename vs name)
        if hasattr(request.app.state.graph_store, 'delete_document'):
            request.app.state.graph_store.delete_document(safe_filename)
        else:
            # Fallback (corrected property name)
            query = "MATCH (d:Document {filename: $name}) DETACH DELETE d"
            request.app.state.graph_store.query(query, {"name": safe_filename})
        
        return {"status": "deleted", "filename": safe_filename}
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    import webbrowser
    import threading
    import time

    def open_browser():
        time.sleep(1.5)
        webbrowser.open(f"http://{settings.HOST}:{settings.PORT}")

    # Auto-open browser in a separate thread to not block uvicorn
    threading.Thread(target=open_browser, daemon=True).start()
    
    uvicorn.run("server:app", host=settings.HOST, port=settings.PORT, reload=True)
