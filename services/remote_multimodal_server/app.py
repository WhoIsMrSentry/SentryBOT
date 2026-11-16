from __future__ import annotations

from remote_multimodal.server import create_app, run_app


def get_app():
    return create_app(lazy_backends=True)


app = create_app(lazy_backends=True)


if __name__ == "__main__":
    run_app()
