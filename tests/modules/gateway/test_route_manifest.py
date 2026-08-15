from fastapi import FastAPI

from modules.gateway.api.router import ROUTE_MANIFEST, get_router


def test_core_route_manifest_matches_registered_routes():
    router = get_router({"server": {"port": 9}}, {})

    registered = {
        (route.path, method)
        for route in router.routes
        for method in (getattr(route, "methods", set()) or set())
        if route.path in {item["path"] for item in ROUTE_MANIFEST}
    }
    declared = {(item["path"], item["method"]) for item in ROUTE_MANIFEST}

    assert registered == declared
    assert all(set(item) == {"path", "method", "auth", "estop_required"} for item in ROUTE_MANIFEST)
    assert all(item["auth"] == "none" and item["estop_required"] is False for item in ROUTE_MANIFEST)