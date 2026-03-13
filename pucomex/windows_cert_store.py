"""Utilitários para certificados instalados no repositório do Windows."""

import json
import os
import platform
import subprocess
from pathlib import Path


class WindowsCertificateStoreError(RuntimeError):
    pass


def _ensure_windows() -> None:
    if platform.system().lower() != 'windows':
        raise WindowsCertificateStoreError('Repositório de certificados do Windows disponível apenas no Windows.')


def list_installed_certificates() -> list[dict]:
    """
    Lista certificados em CurrentUser\My com chave privada.

    Retorna lista com: thumbprint, subject, issuer, not_after.
    """
    _ensure_windows()

    ps_cmd = r"""
$certs = Get-ChildItem Cert:\CurrentUser\My |
  Where-Object { $_.HasPrivateKey -eq $true } |
  Sort-Object NotAfter -Descending |
  Select-Object Thumbprint, Subject, Issuer, NotAfter
$certs | ConvertTo-Json -Depth 3
"""

    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_cmd],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise WindowsCertificateStoreError(result.stderr.strip() or 'Falha ao listar certificados do Windows.')

    raw = result.stdout.strip()
    if not raw:
        return []

    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data]

    output = []
    for item in data:
        output.append({
            'thumbprint': (item.get('Thumbprint') or '').strip().upper(),
            'subject': item.get('Subject') or '',
            'issuer': item.get('Issuer') or '',
            'not_after': item.get('NotAfter') or '',
        })
    return output


def export_certificate_to_pfx(thumbprint: str, destination_pfx: str, password: str) -> None:
    """
    Exporta certificado por thumbprint para PFX temporário.

    Observação: depende da chave privada ser exportável no Windows.
    """
    _ensure_windows()

    thumb = (thumbprint or '').replace(' ', '').upper()
    if not thumb:
        raise WindowsCertificateStoreError('Thumbprint não informado.')

    destination = str(Path(destination_pfx))
    os.makedirs(str(Path(destination).parent), exist_ok=True)

    ps_cmd = rf"""
$thumb = '{thumb}'
$pwd = ConvertTo-SecureString '{password}' -AsPlainText -Force
$cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object {{ $_.Thumbprint -eq $thumb }} | Select-Object -First 1
if (-not $cert) {{ throw 'Certificado não encontrado no repositório CurrentUser\\My.' }}
Export-PfxCertificate -Cert $cert -FilePath '{destination}' -Password $pwd -Force | Out-Null
"""

    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_cmd],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        err = (result.stderr or '').strip()
        if not err:
            err = 'Falha ao exportar certificado para PFX.'
        raise WindowsCertificateStoreError(err)
