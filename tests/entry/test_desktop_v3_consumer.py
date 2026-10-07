"""Public consumer expectations frozen for Desktop v3, independent of App source.

This is backend-owned test code. The private App gate separately runs its
actual current and pinned historical proxies against the same HTTP server.
"""
import asyncio
import json
import socket

import pytest

httpx = pytest.importorskip("httpx")
uvicorn = pytest.importorskip("uvicorn")
pytest.importorskip("fastapi")

from tests.entry.desktop_compat_server import compatibility_app


def test_v3_consumer_health_chat_approval_and_abort(tmp_path):
    async def scenario():
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        server = uvicorn.Server(uvicorn.Config(compatibility_app(tmp_path), log_level='warning', ws='none'))
        serving = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            while not server.started:
                await asyncio.sleep(.01)
            async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{listener.getsockname()[1]}', timeout=10) as client:
                health = (await client.get('/health')).json()
                assert health['status'] == 'ok'
                chat = health['contracts']['desktop_chat']
                assert (chat['request_schema_version'], chat['sse_schema_version'], chat['interrupt_schema_version']) == (3, 3, 1)
                for key in ('provider', 'model', 'python_executable', 'skill_python_executable', 'omicsclaw_dir', 'launch_id'):
                    assert isinstance(health[key], str)
                assert chat['abandon_grace_s'] == 30
                for index, prompt in enumerate(('hello', 'approval', 'abort'), 1):
                    body = {'ingress_schema_version': 3, 'source_request_id': f'{index:032x}', 'session_id': f'consumer-{index}', 'content': prompt}
                    frames = []
                    async with client.stream('POST', '/chat/stream', json=body) as response:
                        assert response.status_code == 200
                        assert response.headers['content-type'].startswith('text/event-stream')
                        async for line in response.aiter_lines():
                            if not line.startswith('data: '):
                                continue
                            frame = json.loads(line[6:])
                            assert isinstance(frame['data'], str)
                            frames.append(frame)
                            if frame['type'] == 'permission_request':
                                card = json.loads(frame['data'])
                                answer = await client.post('/chat/permission', json={'request_id': card['request_id'], 'decision': {'behavior': 'allow', 'scope': 'once'}})
                                assert answer.json()['ok'] is True
                            if prompt == 'abort' and frame['type'] == 'tool_use':
                                answer = await client.post('/chat/abort', json={'session_id': body['session_id'], 'source_request_id': body['source_request_id']})
                                assert answer.json()['state'] == 'cancelling'
                    assert frames[-1] == {'type': 'done', 'data': ''}
                    if prompt == 'abort':
                        assert frames[-2] == {'type': 'error', 'data': 'cancelled'}
                    else:
                        text = ''.join(frame['data'] for frame in frames if frame['type'] == 'text')
                        assert text == ('compatibility hello' if prompt == 'hello' else 'approved: ask ran')
                        assert frames[-2]['type'] == 'result'
                        if prompt == 'approval':
                            results = [json.loads(frame['data']) for frame in frames if frame['type'] == 'tool_result']
                            assert len(results) == 1
                            assert results[0]['content'] == 'ask ran'
                            assert results[0].get('is_error', False) is False
        finally:
            server.should_exit = True
            await asyncio.wait_for(serving, 10)
    asyncio.run(asyncio.wait_for(scenario(), 30))
