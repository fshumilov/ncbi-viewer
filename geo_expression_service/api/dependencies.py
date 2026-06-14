import httpx
from fastapi import Request

from geo_expression_service.config import Settings
from geo_expression_service.services.expression_service import ExpressionService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


def get_expression_service(request: Request) -> ExpressionService:
    return request.app.state.expression_service
