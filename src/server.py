from __future__ import annotations

import json
import sys
from typing import Any, Callable, Optional, Union

from loguru import logger

from .models import ERROR_CODES


class StdioServer:
    def __init__(self) -> None:
        self.buffer = ""
        self.decoder = json.JSONDecoder()
        self._stdin = sys.stdin
        self._stdout = sys.stdout

    def read_message(self) -> Optional[Union[dict[str, Any], list[dict[str, Any]]]]:
        while True:
            try:
                line = self._stdin.readline()
                if not line:
                    return None

                self.buffer += line

                if not self.buffer.strip():
                    continue

                try:
                    message, index = self.decoder.raw_decode(self.buffer)
                    self.buffer = self.buffer[index:].lstrip()
                    return message
                except json.JSONDecodeError:
                    if "\n" in self.buffer and len(self.buffer) > 10000:
                        logger.error("Buffer overflow, clearing")
                        self.buffer = ""
                        return {
                            "jsonrpc": "2.0",
                            "error": {
                                "code": ERROR_CODES["PARSE_ERROR"],
                                "message": "Buffer overflow",
                            },
                            "id": None,
                        }
                    if "\n" in self.buffer:
                        logger.error("JSON parse error, clearing buffer")
                        self.buffer = ""
                    continue

            except KeyboardInterrupt:
                return None
            except Exception as e:
                logger.error(f"Error reading message: {e}")
                self.buffer = ""
                return None

    def send_response(self, response: Optional[Union[dict[str, Any], list[dict[str, Any]]]]) -> None:
        if response is None:
            return
        try:
            output = json.dumps(response)
            self._stdout.write(output + "\n")
            self._stdout.flush()
        except Exception as e:
            logger.error(f"Error sending response: {e}")

    def run(self, handler: Callable[[dict[str, Any]], Optional[dict[str, Any]]]) -> None:
        logger.info("MCP Server starting...")
        while True:
            message = self.read_message()
            if message is None:
                logger.info("Server shutting down")
                break
            try:
                if isinstance(message, list):
                    responses = [
                        r for msg in message if (r := handler(msg)) is not None
                    ]
                    if responses:
                        self.send_response(responses)
                else:
                    response = handler(message)
                    if response is not None:
                        self.send_response(response)
            except Exception as e:
                logger.error(f"Handler error: {e}")
                error_response = {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": ERROR_CODES["INTERNAL_ERROR"],
                        "message": str(e),
                    },
                    "id": message.get("id") if isinstance(message, dict) else None,
                }
                self.send_response(error_response)
