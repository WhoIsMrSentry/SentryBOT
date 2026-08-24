from modules.expression.api.router import get_router
from modules.expression.semantic.services.arbitrator import ExpressionArbiter, ModalityClients


def test_set_arbiter_enables_express_route():
    router = get_router()
    arb = ExpressionArbiter(ModalityClients())
    router.set_arbiter(arb)
    names = {getattr(route, "name", "") for route in router.routes}
    assert "express" in names or any("/express" in str(getattr(route, "path", "")) for route in router.routes)
