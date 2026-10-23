from typing import Generic,TypeVar
from pydantic import BaseModel

T = TypeVar("T")

#通用返回类Result
class Result(BaseModel,Generic[T]):
    code: int
    message: str
    data: T | None = None
    requestId: str

    @classmethod
    def success(cls, data=None, request_id=""):
        return cls(code=0, message="success", data=data,requestId=request_id)
    @classmethod
    def fail(cls, message="fail", request_id=""):
        return cls(code=1, message=message, data=None,requestId=request_id)

#分页返回类PageResult
class PageResult(BaseModel,Generic[T]):
    items: list[T]
    nextCursor: str | None = None
    hasMore: bool