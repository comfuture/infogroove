from infogroove import Infogroove, InfogrooveRenderer, get_version, load, loads, render_svg


def test_get_version_returns_fallback(monkeypatch):
    class Boom(Exception):
        pass

    def fail(name):  # pragma: no cover - executed when patched
        raise Boom

    from importlib import metadata

    monkeypatch.setattr(metadata, "version", fail)
    monkeypatch.setattr(metadata, "PackageNotFoundError", Boom)

    assert get_version() == "0.0.0"


def test_public_api_exports():
    assert isinstance(InfogrooveRenderer, type)
    assert callable(Infogroove)
    assert callable(load)
    assert callable(loads)
    assert callable(render_svg)
