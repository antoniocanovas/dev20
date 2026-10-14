import logging

import requests

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AiProvider(models.Model):
    """Adds ``temperature`` support to odoo_mcp_manager's chat handlers.

    odoo_mcp_manager (third-party, never modified directly — see its own
    README) builds each ``_handle_<service>_chat`` request payload from
    scratch and never forwards a ``temperature`` kwarg to the underlying
    API, even though ``ai.provider.chat()`` already accepts arbitrary
    ``**kwargs``. wizard/domain_chat_mixin.py::_classify wants
    ``temperature=0`` so the same question always classifies to the same
    domain/parameters instead of drifting between calls.

    There is no smaller extension point to hook into: each handler builds
    and sends its own HTTP request in one go, so the only way to add a
    field to that payload without touching odoo_mcp_manager's file is to
    fully override the method here. These four methods otherwise mirror
    the upstream implementation exactly (same base URLs, same response
    parsing) — if odoo_mcp_manager changes how a handler builds its
    payload in a future update, this file needs to be re-synced by hand.
    """

    _inherit = 'ai.provider'

    def _handle_openai_chat(self, messages: list, model: str = None, **kwargs) -> str:
        self.ensure_one()
        base = (self.api_base or 'https://api.openai.com/v1').rstrip('/')
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        data = {
            'model': model or 'gpt-4o',
            'messages': messages,
            'stream': kwargs.get('stream', False),
        }
        if kwargs.get('temperature') is not None:
            data['temperature'] = kwargs['temperature']
        try:
            response = requests.post(
                f'{base}/chat/completions', headers=headers, json=data, timeout=30
            )
            response.raise_for_status()
            return response.json()['choices'][0]['message']['content']
        except requests.RequestException as e:
            _logger.exception('OpenAI API Error')
            raise UserError(_('OpenAI API Error: %s') % str(e))

    def _handle_custom_chat(self, messages: list, model: str = None, **kwargs) -> str:
        return self._handle_openai_chat(messages, model=model, **kwargs)

    def _handle_google_chat(self, messages: list, model: str = None, **kwargs) -> str:
        self.ensure_one()
        base = (
            self.api_base or 'https://generativelanguage.googleapis.com/v1beta'
        ).rstrip('/')
        model_id = model or 'gemini-2.5-flash'
        contents = [
            {
                'role': 'model' if msg.get('role') in ('assistant', 'model') else 'user',
                'parts': [{'text': msg.get('content', '')}],
            }
            for msg in messages
        ]
        payload = {'contents': contents}
        if kwargs.get('temperature') is not None:
            payload['generationConfig'] = {'temperature': kwargs['temperature']}
        try:
            response = requests.post(
                f'{base}/models/{model_id}:generateContent',
                params={'key': self.api_key},
                json=payload,
                timeout=(10, 90),
            )
            response.raise_for_status()
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        except requests.RequestException as e:
            _logger.exception('Google Gemini API Error')
            raise UserError(_('Google Gemini API Error: %s') % str(e))

    def _handle_anthropic_chat(self, messages: list, model: str = None, **kwargs) -> str:
        self.ensure_one()
        base = (self.api_base or 'https://api.anthropic.com/v1').rstrip('/')
        headers = {
            'x-api-key': self.api_key,
            'anthropic-version': '2023-06-01',
            'Content-Type': 'application/json',
        }
        data = {
            'model': model or 'claude-sonnet-4-6',
            'max_tokens': kwargs.get('max_tokens', 1024),
            'messages': messages,
        }
        if kwargs.get('temperature') is not None:
            data['temperature'] = kwargs['temperature']
        try:
            response = requests.post(
                f'{base}/messages', headers=headers, json=data, timeout=30
            )
            response.raise_for_status()
            return response.json()['content'][0]['text']
        except requests.RequestException as e:
            _logger.exception('Anthropic API Error')
            raise UserError(_('Anthropic API Error: %s') % str(e))

    def _handle_ollama_chat(self, messages: list, model: str = None, **kwargs) -> str:
        self.ensure_one()
        base = (self.api_base or 'http://localhost:11434/api').rstrip('/')
        data = {
            'model': model or 'llama3',
            'messages': messages,
            'stream': False,
        }
        if kwargs.get('json_mode'):
            data['format'] = 'json'
        if kwargs.get('temperature') is not None:
            data['options'] = {'temperature': kwargs['temperature']}
        try:
            response = requests.post(f'{base}/chat', json=data, timeout=180)
            response.raise_for_status()
            return response.json()['message']['content']
        except requests.RequestException as e:
            _logger.exception('Ollama API Error')
            raise UserError(_('Ollama API Error: %s') % str(e))
