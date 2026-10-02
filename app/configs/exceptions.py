"""
全局异常处理
统一处理应用异常，返回友好的错误信息
"""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
import traceback
import logging

logger = logging.getLogger(__name__)


class AppException(Exception):
    """应用自定义异常基类"""
    def __init__(self, message: str, status_code: int = 400, details: dict = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class TaskNotFoundException(AppException):
    """任务不存在异常"""
    def __init__(self, task_id: str):
        super().__init__(
            message=f"任务不存在: {task_id}",
            status_code=404,
            details={"task_id": task_id}
        )


class TaskAlreadyExistsException(AppException):
    """任务已存在异常"""
    def __init__(self, task_id: str):
        super().__init__(
            message=f"任务已存在: {task_id}",
            status_code=409,
            details={"task_id": task_id}
        )


class InvalidTaskStatusException(AppException):
    """无效任务状态异常"""
    def __init__(self, task_id: str, current_status: str, expected_status: str):
        super().__init__(
            message=f"任务状态无效，当前: {current_status}，期望: {expected_status}",
            status_code=400,
            details={
                "task_id": task_id,
                "current_status": current_status,
                "expected_status": expected_status
            }
        )


class ModelNotFoundException(AppException):
    """模型不存在异常"""
    def __init__(self, model_name: str):
        super().__init__(
            message=f"不支持的模型: {model_name}",
            status_code=400,
            details={"model_name": model_name}
        )


class APIKeyMissingException(AppException):
    """API Key 缺失异常"""
    def __init__(self, service: str):
        super().__init__(
            message=f"缺少 {service} 的 API Key",
            status_code=401,
            details={"service": service}
        )


def setup_exception_handlers(app: FastAPI):
    """配置全局异常处理器"""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        """处理自定义应用异常"""
        logger.warning(f"AppException: {exc.message}", extra={
            "path": request.url.path,
            "method": request.method,
            "details": exc.details
        })
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": exc.message,
                "details": exc.details,
                "type": exc.__class__.__name__
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """处理请求参数验证异常"""
        logger.warning(f"ValidationError: {exc.errors()}", extra={
            "path": request.url.path,
            "method": request.method
        })
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "error": "请求参数验证失败",
                "details": exc.errors(),
                "type": "ValidationError"
            }
        )

    @app.exception_handler(ValidationError)
    async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
        """处理 Pydantic 验证异常"""
        logger.warning(f"PydanticValidationError: {exc.errors()}", extra={
            "path": request.url.path,
            "method": request.method
        })
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "error": "数据验证失败",
                "details": exc.errors(),
                "type": "PydanticValidationError"
            }
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """处理所有未捕获的异常"""
        error_trace = traceback.format_exc()
        logger.error(f"Unhandled Exception: {str(exc)}\n{error_trace}", extra={
            "path": request.url.path,
            "method": request.method,
            "exception_type": exc.__class__.__name__
        })

        # 开发环境返回详细错误，生产环境只返回简单错误
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": "服务器内部错误",
                "message": str(exc) if app.debug else "请稍后重试或联系管理员",
                "type": exc.__class__.__name__
            }
        )

    logger.info("全局异常处理器已配置")
