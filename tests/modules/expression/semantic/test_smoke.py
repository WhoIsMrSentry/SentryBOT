from __future__ import annotations

from modules.expression.semantic.xExpressionService import create_app, xExpressionService


def test_expression_semantic_create_app():
    app = create_app()
    assert app is not None


def test_expression_semantic_service():
    svc = xExpressionService()
    assert svc is not None
    assert svc.engine is not None

