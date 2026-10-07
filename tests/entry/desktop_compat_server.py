"""Hermetic Desktop process used by the public and private compatibility gates.

Run from this checkout with ``python -m tests.entry.desktop_compat_server``.
Only a scripted provider and harmless test tools are registered.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from omicsclaw.entry.desktop import create_desktop_app
from omicsclaw.entry.session import attach_sessions
from omicsclaw.provider import Completion
from omicsclaw.schema import Message, Role
from tests.entry.test_turn_runner import Asking, Scripted, Sleeping, calling, make_app


class CompatibilityProvider(Scripted):
    async def generate(self, messages, tools=None):
        prompt = next((message.content for message in reversed(messages) if message.role is Role.USER), '')
        if messages[-1].role is Role.TOOL:
            reply = Message(role=Role.ASSISTANT, content='approved: ask ran')
        elif prompt == 'approval':
            reply = calling('ask')
        elif prompt == 'abort':
            reply = calling('sleep')
        else:
            reply = Message(role=Role.ASSISTANT, content='compatibility hello')
        return Completion(message=reply)


def compatibility_app(workspace: Path):
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / 'result.txt').write_text('compatibility file\n')
    app = make_app(workspace, CompatibilityProvider(), tools=[Asking(), Sleeping()])
    return create_desktop_app(attach_sessions(app, abandon_grace_s=30))


def main():
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', required=True, type=int)
    parser.add_argument('--workspace', required=True, type=Path)
    args = parser.parse_args()
    uvicorn.run(compatibility_app(args.workspace), host='127.0.0.1', port=args.port, log_level='warning', ws='none')


if __name__ == '__main__':
    main()
