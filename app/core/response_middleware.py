"""
响应中间件
Response Middleware

用于记录请求日志、生成 TraceID 和计算请求耗时
"""

import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from app.core.logger import logger
from app.core.config import get_config

class ResponseLoggerMiddleware(BaseHTTPMiddleware):
    """
    请求日志/响应追踪中间件
    Request Logging and Response Tracking Middleware
    """
    
    async def dispatch(self, request: Request, call_next):
        # 生成请求 ID
        trace_id = str(uuid.uuid4())
        request.state.trace_id = trace_id
        
        start_time = time.time()
        
        log_health_requests = bool(get_config("log.log_health_requests", False))
        skip_health_log = request.url.path == "/health" and not log_health_requests

        # 记录请求信息
        if not skip_health_log:
            logger.info(
                f"Request: {request.method} {request.url.path}",
                extra={
                    "traceID": trace_id,
                    "method": request.method,
                    "path": request.url.path
                }
            )
        
        try:
            response = await call_next(request)
            
            # 计算耗时
            duration = (time.time() - start_time) * 1000
            
            # 记录响应信息
            if not skip_health_log:
                logger.info(
                    f"Response: {request.method} {request.url.path} - {response.status_code} ({duration:.2f}ms)",
                    extra={
                        "traceID": trace_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status": response.status_code,
                        "duration_ms": round(duration, 2)
                    }
                )
            
            return response
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            logger.error(
                f"Response Error: {request.method} {request.url.path} - {str(e)} ({duration:.2f}ms)",
                extra={
                    "traceID": trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration, 2),
                    "error": str(e)
                }
            )
            raise e
