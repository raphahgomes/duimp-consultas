"""
Autenticação no Portal Único Siscomex.

Suporta dois métodos:
  1. Chave de Acesso (id_chave + chave_secreta) — recomendado para sistemas de terceiros
  2. mTLS com certificado A1 (arquivo PFX/P12) — alternativo

Documentação oficial: https://docs.portalunico.siscomex.gov.br/api/plat/

Comportamento dos tokens:
  - JWT: retornado no header `Set-Token` da resposta de autenticação.
  - X-CSRF-Token: retornado no header `X-CSRF-Token`; deve ser renovado a cada
    requisição — o portal devolve um novo token no header da resposta.
  - Tempo de validade: 60 minutos.
  - Reautenticação antes de 60s retorna erro PLAT-ER2033.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

PORTAL_BASE_URL = 'https://portalunico.siscomex.gov.br'
AUTH_CHAVE_URL = f'{PORTAL_BASE_URL}/portal/api/autenticar/chave-acesso'
AUTH_MTLS_URL = f'{PORTAL_BASE_URL}/portal/api/autenticar'
TOKEN_EXPIRY_MINUTES = 58  # margem de 2 minutos antes do vencimento real (60 min)


class PucomexSession:
    """
    Sessão autenticada no Portal Único.

    Gerencia JWT e X-CSRF-Token automaticamente:
    - Armazena os tokens após autenticação
    - Renova X-CSRF-Token a partir do header de cada resposta
    - Expõe `get`, `post` com os headers corretos injetados automaticamente
    """

    def __init__(self, role_type: str = 'IMPEXP'):
        self._session = requests.Session()
        self._jwt: Optional[str] = None
        self._csrf: Optional[str] = None
        self._expires_at: Optional[datetime] = None
        self.role_type = role_type

    # ── Estado da sessão ───────────────────────────────────────────────────

    @property
    def is_authenticated(self) -> bool:
        if not self._jwt or not self._expires_at:
            return False
        return datetime.now(tz=timezone.utc) < self._expires_at

    def _store_tokens(self, response: requests.Response) -> None:
        jwt = response.headers.get('Set-Token')
        csrf = response.headers.get('X-CSRF-Token')
        if jwt:
            self._jwt = jwt
        if csrf:
            self._csrf = csrf
        self._expires_at = datetime.now(tz=timezone.utc) + timedelta(minutes=TOKEN_EXPIRY_MINUTES)
        logger.debug('Tokens armazenados. Expiram em %s', self._expires_at.isoformat())

    # ── Autenticação ───────────────────────────────────────────────────────

    def authenticate_chave_acesso(self, id_chave: str, chave_secreta: str) -> None:
        """
        Autentica usando par de chaves gerado no portal (sem certificado digital).

        Parâmetros
        ----------
        id_chave      : identificador da chave (obtido no portal)
        chave_secreta : segredo correspondente (obtido no portal, armazenado criptografado)
        """
        payload = {'id': id_chave, 'secret': chave_secreta}
        headers = {'Content-Type': 'application/json', 'Role-Type': self.role_type}

        response = self._session.post(AUTH_CHAVE_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        self._store_tokens(response)
        logger.info('Autenticado via chave de acesso.')

    def authenticate_mtls(self, pfx_path: str, pfx_password: str) -> None:
        """
        Autentica usando certificado digital A1 (arquivo PFX/P12).

        O arquivo PFX é convertido para PEM em memória — nunca gravado em disco.

        Parâmetros
        ----------
        pfx_path     : caminho para o arquivo .pfx / .p12
        pfx_password : senha do certificado
        """
        import tempfile
        import os
        from cryptography.hazmat.primitives.serialization import (
            Encoding, PrivateFormat, NoEncryption
        )
        from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates

        with open(pfx_path, 'rb') as f:
            pfx_data = f.read()

        private_key, certificate, _ = load_key_and_certificates(
            pfx_data, pfx_password.encode()
        )

        # Exporta para PEM em memória, grava em arquivos temporários para requests
        cert_pem = certificate.public_bytes(Encoding.PEM)
        key_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())

        # requests exige arquivos em disco para mTLS — usa temporários
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pem') as cert_file, \
             tempfile.NamedTemporaryFile(delete=False, suffix='.pem') as key_file:
            cert_file.write(cert_pem)
            key_file.write(key_pem)
            cert_tmp = cert_file.name
            key_tmp = key_file.name

        try:
            headers = {'Role-Type': self.role_type}
            response = self._session.post(
                AUTH_MTLS_URL,
                headers=headers,
                cert=(cert_tmp, key_tmp),
                timeout=30
            )
            response.raise_for_status()
            self._store_tokens(response)
            logger.info('Autenticado via mTLS.')
        finally:
            os.unlink(cert_tmp)
            os.unlink(key_tmp)

    # ── Requisições autenticadas ───────────────────────────────────────────

    def _build_headers(self, extra: Optional[dict] = None) -> dict:
        if not self.is_authenticated:
            raise RuntimeError('Sessão não autenticada ou expirada.')
        headers = {
            'Authorization': self._jwt,
            'X-CSRF-Token': self._csrf or '',
            'Role-Type': self.role_type,
        }
        if extra:
            headers.update(extra)
        return headers

    def get(self, url: str, **kwargs) -> requests.Response:
        headers = self._build_headers(kwargs.pop('headers', None))
        response = self._session.get(url, headers=headers, timeout=30, **kwargs)
        # Renova X-CSRF-Token a partir da resposta
        new_csrf = response.headers.get('X-CSRF-Token')
        if new_csrf:
            self._csrf = new_csrf
        return response

    def post(self, url: str, **kwargs) -> requests.Response:
        headers = self._build_headers(kwargs.pop('headers', None))
        response = self._session.post(url, headers=headers, timeout=30, **kwargs)
        new_csrf = response.headers.get('X-CSRF-Token')
        if new_csrf:
            self._csrf = new_csrf
        return response
