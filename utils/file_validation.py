from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from django.core.exceptions import ValidationError


DANGEROUS_EXTENSIONS = {
    'asp', 'aspx', 'bat', 'cmd', 'com', 'cpl', 'dll', 'exe', 'hta',
    'jar', 'jsp', 'jse', 'msi', 'php', 'php3', 'php4', 'php5', 'phar',
    'phtml', 'ps1', 'sh', 'shtml', 'vbs', 'war'
}


def _normalize_extensions(values: Iterable[str] | None) -> set[str]:
    return {str(value).lower().lstrip('.') for value in values or [] if str(value).strip()}


def validate_uploaded_file(
    file_obj,
    *,
    allowed_extensions: Iterable[str] | None = None,
    allowed_mime_types: Iterable[str] | None = None,
    max_size_bytes: int | None = None,
    field_label: str = 'File',
) -> None:
    if file_obj is None:
        return

    file_name = Path(getattr(file_obj, 'name', '') or '').name
    if not file_name:
        raise ValidationError(f'{field_label} name is invalid.')

    file_size = int(getattr(file_obj, 'size', 0) or 0)
    if file_size <= 0:
        raise ValidationError(f'{field_label} cannot be empty.')

    if max_size_bytes is not None and file_size > max_size_bytes:
        raise ValidationError(f'{field_label} must be smaller than {max_size_bytes // (1024 * 1024)} MB.')

    extension_parts = [part.lower() for part in file_name.split('.') if part]
    if len(extension_parts) < 2:
        raise ValidationError(f'{field_label} must have a valid file extension.')

    final_extension = extension_parts[-1]
    allowed_extension_set = _normalize_extensions(allowed_extensions)
    if allowed_extension_set and final_extension not in allowed_extension_set:
        raise ValidationError(f'{field_label} has an unsupported file extension.')

    blocked_segments = set(extension_parts[:-1]) & DANGEROUS_EXTENSIONS
    if blocked_segments:
        raise ValidationError(f'{field_label} contains a blocked extension.')

    mime_type = (
        getattr(file_obj, 'content_type', None)
        or getattr(file_obj, 'mimetype', None)
        or mimetypes.guess_type(file_name)[0]
        or ''
    ).lower()
    allowed_mime_set = {str(value).lower() for value in allowed_mime_types or [] if str(value).strip()}
    if allowed_mime_set and mime_type not in allowed_mime_set:
        raise ValidationError(f'{field_label} has an unsupported file type.')


def secure_upload_filename(filename: str, subdirectory: str) -> str:
    file_name = Path(filename or 'upload.bin').name
    extension = Path(file_name).suffix
    safe_extension = extension.lower() if extension else '.bin'
    return f'{subdirectory}/{uuid4().hex[:12]}{safe_extension}'
