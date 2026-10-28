import argparse

from .config_loader import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Speaker-ID service (voiceprint MVP)")
    parser.add_argument("--config", type=str, default=None)
    args = parser.parse_args()
    cfg = load_config(args.config)
    import uvicorn

    from .api.router import get_router
    from .xSpeakerIdService import SpeakerIdService
    from fastapi import FastAPI

    app = FastAPI(title="Speaker-ID Service")
    app.include_router(get_router(SpeakerIdService(args.config)))
    server = cfg.get("server", {})
    uvicorn.run(app, host=str(server.get("host", "127.0.0.1")), port=int(server.get("port", 8087)), log_config=None)


if __name__ == "__main__":
    main()
