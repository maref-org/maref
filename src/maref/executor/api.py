from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi import status as http_status
from pydantic import BaseModel, Field

from maref.executor.queue import TaskQueue
from maref.executor.types import Task, TaskPriority, TaskStatus


class TaskCreate(BaseModel):
    name: str
    description: str = ""
    priority: int = Field(default=1, ge=0, le=3)
    payload: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float | None = None
    max_retries: int = Field(default=0, ge=0)
    tags: list[str] = Field(default_factory=list)
    session_id: str | None = None


class TaskResponse(BaseModel):
    id: str
    name: str
    description: str
    priority: int
    status: str
    payload: dict[str, Any]
    created_at: str
    updated_at: str
    started_at: str | None
    completed_at: str | None
    timeout_seconds: float | None
    max_retries: int
    retry_count: int
    error_message: str | None
    session_id: str | None
    tags: list[str]


class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]
    total: int


class CancelResponse(BaseModel):
    task_id: str
    status: str


class ErrorResponse(BaseModel):
    detail: str


def _task_to_response(task: Task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        name=task.name,
        description=task.description,
        priority=task.priority.value,
        status=task.status.value,
        payload=task.payload,
        created_at=task.created_at,
        updated_at=task.updated_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        timeout_seconds=task.timeout_seconds,
        max_retries=task.max_retries,
        retry_count=task.retry_count,
        error_message=task.error_message,
        session_id=task.session_id,
        tags=task.tags,
    )


def create_task_router(task_queue: TaskQueue) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/tasks", status_code=http_status.HTTP_201_CREATED)  # type: ignore[untyped-decorator]
    def create_task(task_data: TaskCreate, request: Request) -> dict[str, str]:
        task = Task(
            name=task_data.name,
            description=task_data.description,
            priority=TaskPriority(task_data.priority),
            payload=task_data.payload,
            timeout_seconds=task_data.timeout_seconds,
            max_retries=task_data.max_retries,
            tags=task_data.tags,
            session_id=task_data.session_id,
        )
        client_host = request.client.host if request.client else "unknown"
        task.metadata["source"] = client_host
        task_id = task_queue.enqueue(task)
        return {
            "task_id": task_id,
            "status": task.status.value,
            "created_at": task.created_at,
        }

    @router.get("/api/v1/tasks/{task_id}")  # type: ignore[untyped-decorator]
    def get_task(task_id: str) -> TaskResponse:
        task = task_queue.get(task_id)
        if task is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Task {task_id} not found",
            )
        return _task_to_response(task)

    @router.post("/api/v1/tasks/{task_id}/cancel")  # type: ignore[untyped-decorator]
    def cancel_task(task_id: str) -> CancelResponse:
        task = task_queue.get(task_id)
        if task is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Task {task_id} not found",
            )
        if task.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.TIMEOUT,
        ):
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail=(
                    f"Task {task_id} is already in status {task.status.value}"
                ),
            )
        if task.status not in (TaskStatus.QUEUED, TaskStatus.PENDING):
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail=(
                    f"Task {task_id} cannot be cancelled in status"
                    f" {task.status.value}"
                ),
            )
        task_queue.update_status(task_id, TaskStatus.CANCELLED)
        return CancelResponse(task_id=task_id, status="cancelled")

    @router.get("/api/v1/tasks")  # type: ignore[untyped-decorator]
    def list_tasks(
        status: str | None = None,
        priority: int | None = None,
        session_id: str | None = None,
        tag: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> TaskListResponse:
        if limit > 1000:
            limit = 1000
        status_enum = TaskStatus(status) if status is not None else None
        priority_enum = (
            TaskPriority(priority) if priority is not None else None
        )
        tasks = task_queue.list_tasks(
            status=status_enum,
            priority=priority_enum,
            limit=limit,
            offset=offset,
            session_id=session_id,
            tag=tag,
        )
        total = task_queue.count_tasks(
            status=status_enum,
            priority=priority_enum,
            session_id=session_id,
            tag=tag,
        )
        return TaskListResponse(
            tasks=[_task_to_response(t) for t in tasks],
            total=total,
        )

    return router
