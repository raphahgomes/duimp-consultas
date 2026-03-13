"""
Sessão HTTP via Windows SChannel (PowerShell).

Permite mTLS com certificados cujas chaves privadas NÃO são exportáveis,
usando Invoke-RestMethod que delega o TLS handshake ao SChannel do Windows.
O navegador e o Portal Único funcionam exatamente assim.
"""

import json
import logging
import platform
import subprocess
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

PORTAL_BASE_URL = 'https://portalunico.siscomex.gov.br'
AUTH_MTLS_URL = f'{PORTAL_BASE_URL}/portal/api/autenticar'
TOKEN_EXPIRY_MINUTES = 58
_AUTH_CACHE: dict[tuple[str, str], dict[str, object]] = {}


class SChannelError(RuntimeError):
    pass


class SChannelResponse:
    """Wrapper compatível com requests.Response para uso no api_duimp.py."""

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self._body = body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise SChannelError(f'HTTP {self.status_code}: {self._body[:500]}')

    def json(self) -> dict | list:
        return json.loads(self._body)


def _ensure_windows() -> None:
    if platform.system().lower() != 'windows':
        raise SChannelError('SChannel disponível apenas no Windows.')


def _powershell(script: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['powershell', '-NoProfile', '-Command', script],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _cache_key(thumbprint: str, role_type: str) -> tuple[str, str]:
    return thumbprint, role_type


def _get_cached_auth(thumbprint: str, role_type: str) -> dict[str, object] | None:
    cached = _AUTH_CACHE.get(_cache_key(thumbprint, role_type))
    if not cached:
        return None
    expires_at = cached.get('expires_at')
    if not isinstance(expires_at, datetime) or datetime.now(tz=timezone.utc) >= expires_at:
        _AUTH_CACHE.pop(_cache_key(thumbprint, role_type), None)
        return None
    return cached


def _set_cached_auth(thumbprint: str, role_type: str, jwt: str, csrf: str | None, cookies: str) -> dict[str, object]:
    cached = {
        'jwt': jwt,
        'csrf': csrf or '',
        'cookies': cookies or '',
        'expires_at': datetime.now(tz=timezone.utc) + timedelta(minutes=TOKEN_EXPIRY_MINUTES),
    }
    _AUTH_CACHE[_cache_key(thumbprint, role_type)] = cached
    return cached


class SChannelSession:
    """
    Sessão autenticada no Portal Único via SChannel (Windows).

    Usa Invoke-RestMethod do PowerShell com -Certificate para mTLS.
    Funciona com chaves privadas não-exportáveis.
    """

    def __init__(self, thumbprint: str, role_type: str = 'IMPEXP'):
        _ensure_windows()
        self.thumbprint = (thumbprint or '').replace(' ', '').upper()
        if not self.thumbprint:
            raise SChannelError('Thumbprint não informado.')
        self.role_type = role_type
        self._jwt: str | None = None
        self._csrf: str | None = None
        self._cookies: str = ''

    def _apply_cached_auth(self) -> bool:
        cached = _get_cached_auth(self.thumbprint, self.role_type)
        if not cached:
            return False
        self._jwt = str(cached.get('jwt') or '') or None
        self._csrf = str(cached.get('csrf') or '') or None
        self._cookies = str(cached.get('cookies') or '')
        return bool(self._jwt)

    def _cache_auth(self) -> None:
        if self._jwt:
            _set_cached_auth(self.thumbprint, self.role_type, self._jwt, self._csrf, self._cookies)

    def authenticate(self) -> None:
        """Autentica no Portal Único via mTLS usando SChannel."""
        if self._apply_cached_auth():
            logger.debug('Reutilizando autenticação SChannel em cache para thumbprint %s...', self.thumbprint[:8])
            return

        ps_script = rf"""
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ErrorActionPreference = 'Stop'
$thumb = '{self.thumbprint}'
$cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object {{ $_.Thumbprint -eq $thumb }} | Select-Object -First 1
if (-not $cert) {{ throw 'Certificado não encontrado no repositório CurrentUser\My.' }}

$headers = @{{ 'Role-Type' = '{self.role_type}' }}

try {{
    $resp = Invoke-WebRequest -Uri '{AUTH_MTLS_URL}' `
        -Method POST `
        -Headers $headers `
        -Certificate $cert `
        -UseBasicParsing `
        -TimeoutSec 30
}} catch {{
    $ex = $_.Exception
    $body = ''
    $errorDetails = ''
    if ($_.ErrorDetails -and $_.ErrorDetails.Message) {{
        $errorDetails = $_.ErrorDetails.Message
    }}
    if ($ex.Response) {{
        $stream = $ex.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        $body = $reader.ReadToEnd()
        $reader.Close()
    }}
    $errResult = @{{
        Error      = $true
        StatusCode = if ($ex.Response) {{ [int]$ex.Response.StatusCode }} else {{ 0 }}
        Body       = if ($errorDetails) {{ $errorDetails }} elseif ($body) {{ $body }} else {{ $ex.Message }}
        Message    = $ex.Message
    }}
    $errResult | ConvertTo-Json -Depth 3
    exit 0
}}

# Captura cookies
$cookies = ''
if ($resp.Headers['Set-Cookie']) {{
    $rawCookies = $resp.Headers['Set-Cookie']
    if ($rawCookies -is [array]) {{
        $cookies = ($rawCookies | ForEach-Object {{ ($_ -split ';')[0] }}) -join '; '
    }} else {{
        $cookies = ($rawCookies -split ';')[0]
    }}
}}

$result = @{{
    StatusCode = $resp.StatusCode
    JWT        = $resp.Headers['Set-Token']
    CSRF       = $resp.Headers['X-CSRF-Token']
    Cookies    = $cookies
}}
$result | ConvertTo-Json -Depth 3
"""
        result = _powershell(ps_script, timeout=45)
        if result.returncode != 0:
            err = (result.stderr or '').strip()
            raise SChannelError(f'Falha na autenticação mTLS via SChannel: {err}')

        stdout = result.stdout.strip()
        if not stdout:
            err = (result.stderr or '').strip()
            raise SChannelError(f'Resposta vazia na autenticação SChannel. stderr: {err}')

        logger.debug('SChannel auth stdout: %s', stdout[:500])
        data = json.loads(stdout)

        # Check if caught error
        if data.get('Error'):
            status = data.get('StatusCode', 0)
            body = data.get('Body', '')
            msg = data.get('Message', '')
            if status == 422 and 'PLAT-ER2033' in body and self._apply_cached_auth():
                logger.debug('Portal recusou reautenticação; reutilizando token SChannel em cache para thumbprint %s...', self.thumbprint[:8])
                return
            raise SChannelError(
                f'Portal retornou HTTP {status} na autenticação. Body: {body[:500]}  Message: {msg}'
            )

        status = data.get('StatusCode')
        if status and int(status) >= 400:
            raise SChannelError(f'Portal retornou HTTP {status} na autenticação.')

        self._jwt = data.get('JWT')
        self._csrf = data.get('CSRF')
        self._cookies = data.get('Cookies') or ''
        if not self._jwt:
            raise SChannelError('Token JWT não recebido na autenticação.')
        self._cache_auth()
        logger.info('Autenticado via SChannel (mTLS) com thumbprint %s...', self.thumbprint[:8])
        logger.debug('Cookies capturados: %s', self._cookies[:200] if self._cookies else '(nenhum)')

    @property
    def is_authenticated(self) -> bool:
        return bool(self._jwt)

    def get(self, url: str, params: dict | None = None, **kwargs) -> SChannelResponse:
        """Faz GET autenticado via SChannel. Retorna SChannelResponse compatível com requests."""
        if not self.is_authenticated:
            raise SChannelError('Sessão não autenticada.')

        # Monta query string
        qs = ''
        if params:
            pairs = '&'.join(f'{k}={v}' for k, v in params.items())
            qs = f'?{pairs}'

        ps_script = rf"""
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ErrorActionPreference = 'Stop'

$thumb = '{self.thumbprint}'
$cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object {{ $_.Thumbprint -eq $thumb }} | Select-Object -First 1
if (-not $cert) {{ throw "Certificado $thumb nao encontrado." }}

$headers = @{{
    'Authorization' = '{self._jwt}'
    'X-CSRF-Token'  = '{self._csrf or ""}'
    'Role-Type'     = '{self.role_type}'
}}
if ('{self._cookies}') {{
    $headers['Cookie'] = '{self._cookies}'
}}

try {{
    $resp = Invoke-WebRequest -Uri ('{url}{qs}') `
        -Method GET `
        -Headers $headers `
        -Certificate $cert `
        -UseBasicParsing `
        -TimeoutSec 30 `
        -ErrorAction Stop
}} catch {{
    $ex = $_.Exception
    $statusCode = 0
    if ($ex.Response) {{ $statusCode = [int]$ex.Response.StatusCode }}
    $body = ''
    $errorDetails = ''
    if ($_.ErrorDetails -and $_.ErrorDetails.Message) {{
        $errorDetails = $_.ErrorDetails.Message
    }}
    if ($ex.Response) {{
        $stream = $ex.Response.GetResponseStream()
        if ($stream) {{
            $reader = New-Object System.IO.StreamReader($stream)
            $body = $reader.ReadToEnd()
            $reader.Close()
        }}
    }}
    $output = @{{
        StatusCode = $statusCode
        Body       = if ($errorDetails) {{ $errorDetails }} elseif ($body) {{ $body }} else {{ $ex.Message }}
        NewCSRF    = $null
        Error      = $true
    }}
    $output | ConvertTo-Json -Depth 1 -Compress
    exit 0
}}

$newCsrf = $resp.Headers['X-CSRF-Token']

$output = @{{
    StatusCode = $resp.StatusCode
    Body       = $resp.Content
    NewCSRF    = $newCsrf
}}
$output | ConvertTo-Json -Depth 1 -Compress
"""
        result = _powershell(ps_script, timeout=60)
        if result.returncode != 0:
            err = (result.stderr or '').strip()
            raise SChannelError(f'Erro no GET {url}: {err}')

        stdout = result.stdout.strip()
        if not stdout:
            err = (result.stderr or '').strip()
            raise SChannelError(f'Resposta vazia no GET {url}. stderr: {err}')

        logger.debug('SChannel GET stdout: %s', stdout[:500])
        wrapper = json.loads(stdout)

        if wrapper.get('Error'):
            raise SChannelError(f'Erro no GET {url}: {wrapper.get("Body", "desconhecido")}')

        status = int(wrapper.get('StatusCode') or 0)

        new_csrf = wrapper.get('NewCSRF')
        if new_csrf:
            self._csrf = new_csrf
            self._cache_auth()

        body = wrapper.get('Body') or '{}'
        return SChannelResponse(status, body)
