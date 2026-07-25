#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地启动 Dashboard：python -m gold_model.web_server [port]"""
import functools
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from gold_model.paths import WEB_DIR


def main(port=8000):
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(WEB_DIR))
    server = ThreadingHTTPServer(('127.0.0.1', port), handler)
    print(f"Dashboard: http://127.0.0.1:{port}  (Ctrl+C 停止)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
