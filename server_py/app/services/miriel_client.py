"""
Miriel API client singleton for QuestAI integration.
Handles all interactions with Miriel's knowledge service for AI-generated storylines.
"""

import base64
import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, Iterator, Optional
from urllib.parse import urlparse

import requests
from requests.exceptions import HTTPError, RequestException

_logger = logging.getLogger(__name__)

PROJECT_NAMESPACE = "questai"

# Test-only seam: when set, query() returns a canned answer instead of making a
# network call. This is for the offline test suite — it is never set at runtime,
# so the real game always talks to Miriel (and fails hard if Miriel is down).
_TEST_RESPONDER = None


def install_test_responder(fn) -> None:
    """fn(query: str) -> str. Pass None to uninstall. Installing one marks the
    client enabled so is_miriel_enabled() reflects the stubbed-but-working AI."""
    global _TEST_RESPONDER
    _TEST_RESPONDER = fn
    if fn is not None:
        get_miriel_client().enabled = True


class UnauthorizedError(Exception):
    pass


class MirielUnavailable(RuntimeError):
    """Raised when a Miriel-backed feature is used but Miriel isn't working
    (unconfigured / unreachable). Surfaced as a hard failure, by design."""


class MirielRequestError(Exception):
    """Generic API error (non-401)."""

    def __init__(self, status_code: int, message: str, body: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class MirielStreamError(Exception):
    """Raised when the SSE stream emits an error event or terminates unexpectedly."""


class MirielClient:
    """Singleton client for Miriel API operations."""

    _instance: Optional['MirielClient'] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.api_key = os.getenv("MIRIEL_API_KEY")
            self.base_url = os.getenv("MIRIEL_API_URL", "https://api.prod.miriel.ai")
            self.api_version = "v2"
            self.verify = True
            self.auto_learning_enabled = os.getenv("MIRIEL_AUTO_LEARNING", "true").lower() == "true"

            if not self.api_key:
                print("[MIRIEL] WARNING: MIRIEL_API_KEY not set. AI features disabled.")
                self.enabled = False
            else:
                self.enabled = True
                print(f"[MIRIEL] Initialized with project: {PROJECT_NAMESPACE}")
                print(f"[MIRIEL] Auto-learning: {self.auto_learning_enabled}")

            self._initialized = True

    # ----------------------------
    # Core request helpers
    # ----------------------------

    def _build_url(self, route: str) -> str:
        return f'{self.base_url}/api/{self.api_version}/{route}'

    @staticmethod
    def _project_param(project) -> list:
        """The API expects `project` as a list of namespaces (was a string)."""
        if project is None:
            return [PROJECT_NAMESPACE]
        if isinstance(project, str):
            return [project]
        return list(project)

    def _apply_auth(self, headers: Optional[Dict[str, str]]) -> Dict[str, str]:
        headers = dict(headers or {})
        headers['x-access-token'] = self.api_key
        return headers

    def _raise_for_status(self, resp: requests.Response) -> None:
        """Raise nice exceptions for non-2xx responses."""
        try:
            resp.raise_for_status()
        except HTTPError as err:
            status = err.response.status_code if err.response is not None else -1
            body = None
            try:
                body = err.response.text if err.response is not None else None
            except Exception:
                body = None

            if status == 401:
                raise UnauthorizedError('Invalid API key. Please visit https://miriel.ai to sign up.') from err

            if status == 501:
                msg = 'Not implemented'
                try:
                    j = err.response.json() if err.response is not None else None
                    if isinstance(j, dict):
                        msg = j.get('error') or j.get('message') or msg
                except Exception:
                    pass
                raise MirielRequestError(status, msg, body=body) from err

            # Surface the API's error body — a bare "(400)" is undebuggable.
            detail = f': {body[:500]}' if body else ''
            raise MirielRequestError(status, f'Miriel request error ({status}){detail}', body=body) from err

    def _request_raw(self, method, route: str, **kwargs) -> requests.Response:
        """Perform an HTTP request and return the Response (no JSON parsing)."""
        url = self._build_url(route)

        headers = kwargs.pop('headers', None)
        kwargs['headers'] = self._apply_auth(headers)

        if 'verify' not in kwargs:
            kwargs['verify'] = self.verify

        resp = method(url, **kwargs)
        self._raise_for_status(resp)
        return resp

    def _request_json(self, method, route: str, **kwargs) -> Dict[str, Any]:
        """Perform an HTTP request and parse JSON."""
        resp = self._request_raw(method, route, **kwargs)
        try:
            return resp.json()
        except ValueError as e:
            _logger.error(f'Error parsing JSON response: status={resp.status_code} body={resp.text[:1000]!r}')
            raise e

    def serialize_payload_for_form(self, payload):
        """Convert all nested dicts/lists in the payload to JSON strings."""
        serialized = {}
        for key, value in (payload or {}).items():
            if isinstance(value, (dict, list)):
                serialized[key] = json.dumps(value)
            else:
                serialized[key] = value
        return serialized

    def make_post_request(self, route, payload=None, files=None):
        """
        Makes a POST request to the given URL.
        - If 'files' is provided, sends a multipart/form-data request
        - Otherwise, sends a JSON body
        """
        if files:
            headers = {'Accept': 'application/json'}
            payload = self.serialize_payload_for_form(payload or {})
            return self._request_json(
                requests.post,
                route,
                headers=headers,
                data=payload,
                files=files,
            )
        else:
            headers = {'Content-Type': 'application/json'}
            return self._request_json(
                requests.post,
                route,
                headers=headers,
                json=payload,
            )

    # ----------------------------
    # Query (non-streaming)
    # ----------------------------

    def query(
        self,
        query: str,
        *,
        timeout: Optional[Any] = None,
        force_exhaustive: bool = False,
        response_format: Optional[dict] = None,
        project: Optional[str] = None,
        **params,
    ):
        """
        Perform a Miriel query (non-streaming).

        Args:
          query: The query string
          timeout: Request timeout
          force_exhaustive: Force exhaustive query mode
          response_format: Custom response schema
          project: Project namespace (defaults to 'questai')

        Returns:
          dict with query response
        """
        projects = self._project_param(project)

        def _do_query():
            if _TEST_RESPONDER is not None:
                return {"results": {"answer": _TEST_RESPONDER(query)}}
            route = 'query'
            payload = {
                'query': query,
                'streaming': False,
                'voice_mode': False,
                'force_exhaustive': force_exhaustive,
                'project': projects,
                **{k: v for k, v in params.items() if v is not None},
            }
            # Only include response_format when set; strict validators reject null.
            if response_format is not None:
                payload['response_format'] = response_format
            return self.make_post_request(route, payload=payload)

        # Single-flight identical concurrent queries (e.g. a background warm and
        # the real look/move/talk for the same scene) so they share one
        # round-trip instead of duplicating the call.
        import hashlib
        from ..single_flight import run as single_flight
        key = "q:" + hashlib.sha256(
            f"{query}|{projects}|{force_exhaustive}".encode()
        ).hexdigest()
        return single_flight(key, _do_query)

    # ----------------------------
    # Learning
    # ----------------------------

    def learn(
        self,
        input_data: str | dict | list,
        user_id=None,
        metadata=None,
        force_string=False,
        discoverable=True,
        grant_ids=['*'],
        priority=100,
        project=None,
        wait_for_complete=False,
        expiration_seconds: Optional[int] = None,
    ):
        """
        Add data to the Miriel AI system for learning.

        Args:
          input_data: String, dict, or list to learn
          metadata: Metadata for filtering/search
          force_string: Always treat input as string
          discoverable: Whether content is discoverable
          grant_ids: Access control IDs
          priority: Priority level (higher = more important)
          project: Project namespace (defaults to 'questai')
          wait_for_complete: Wait for learning job to complete
          expiration_seconds: Optional TTL for learned data

        Returns:
          Response dict from API
        """
        # Format input for new-style API
        if isinstance(input_data, list):
            parsed_inputs = [
                self._format_learn_input(item, expiration_seconds=expiration_seconds)
                for item in input_data
            ]
        else:
            parsed_inputs = [
                self._format_learn_input(input_data, expiration_seconds=expiration_seconds)
            ]

        if isinstance(priority, str):
            if priority == 'norank':
                priority = -1
            elif priority == 'pin':
                priority = -2

        payload = {
            'user_id': user_id,
            'input': parsed_inputs,
            'metadata': metadata,
            'force_string': force_string,
            'discoverable': discoverable,
            'grant_ids': grant_ids,
            'priority': priority,
            'project': self._project_param(project),
        }

        _logger.info(f'[MIRIEL] Learning {len(parsed_inputs)} items...')
        route = 'learn'
        response = self.make_post_request(route, payload=payload)

        return response

    @classmethod
    def _format_learn_input(cls, input_value, upsert_id=None, command=None, expiration_seconds: Optional[int] = None):
        """Helper to ensure proper data structure for learn API."""
        # Convert dicts to JSON strings for learning
        if isinstance(input_value, dict):
            input_value = json.dumps(input_value)

        return {
            'value': input_value,
            'upsert_id': upsert_id,
            'command': command,
            'expiration_seconds': expiration_seconds,
        }

    def remove_document(self, document_id, user_id=None):
        return self.make_post_request('remove_document', payload={'document_id': document_id, 'user_id': user_id})

    def get_all_documents(self, user_id=None, project=None, metadata_query=None):
        payload = {}
        if user_id is not None:
            payload['user_id'] = user_id
        if project is not None:
            payload['project'] = self._project_param(project)
        if metadata_query is not None:
            payload['metadata_query'] = metadata_query
        return self.make_post_request('get_all_documents', payload=payload)


# Global singleton instance
_miriel: Optional[MirielClient] = None


def get_miriel_client() -> MirielClient:
    """Get the global Miriel client instance."""
    global _miriel
    if _miriel is None:
        _miriel = MirielClient()
    return _miriel


def is_miriel_enabled() -> bool:
    """Check if Miriel integration is enabled."""
    client = get_miriel_client()
    return client.enabled
