"""Remote control-plane API for the OmicsClaw desktop App.

Implements the HTTP/SSE contract consumed by ``OmicsClaw-App`` (Stage 0/1
already shipped). Mounted onto ``oc app-server`` via ``include_router`` so
the legacy single-file ``omicsclaw/app/server.py`` stays untouched.
"""
