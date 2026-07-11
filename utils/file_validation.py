from __future__ import annotations

import os
import mimetypes
import uuid
from pathlib import Path

from rest_framework import serializers

_DANGEROUS_EXTENSIONS = {
    '.asp', '.aspx', '.bat', '.cgi', '.cmd', '.com', '.exe', '.hta', '.jar',
    '.jse', '.jsp', '.msi', '.php', '.phtml', '.pl', '.ps1', '.py', '.sh',
    '.shtm', '.shtml', '.vbe', '.vbs', '.wsf', '.wsh'
}


def secure_upload_filename(filename: str, *, default_extension: str = '.bin') -> str:
    base_name = os.path.basename(str(filename or '')).strip()
    extension = Path(base_name).suffix.lower()
    if not extension or len(extension) > 10:
        extension = default_extension
    if not extension.startswith('.'):
        extension = f'.{extension}'
    return f"{uuid.uuid4().hex}{extension}"


def validate_uploaded_file(
    uploaded_file,
    *,
    field_name: str,
    label: str,
    allowed_extensions: set[str],
    allowed_content_types: set[str] | None = None,
    max_size_mb: int = 5,
) -> None:
    if uploaded_file is None:
        return

    file_name = str(getattr(uploaded_file, "name", "") or "")
    if not file_name.strip():
        raise serializers.ValidationError({field_name: f"{label} is required."})

    suffixes = [suffix.lower() for suffix in Path(file_name).suffixes]
    if not suffixes:
        expected = ", ".join(sorted(allowed_extensions))
        raise serializers.ValidationError({field_name: f"{label} must use one of these file types: {expected}."})

    if any(suffix in _DANGEROUS_EXTENSIONS for suffix in suffixes):
        raise serializers.ValidationError({field_name: f"{label} uses a prohibited file type."})

    extension = Path(file_name).suffix.lower()
    if extension not in allowed_extensions:
        expected = ", ".join(sorted(allowed_extensions))
        raise serializers.ValidationError({field_name: f"{label} must use one of these file types: {expected}."})

    file_size = getattr(uploaded_file, "size", None)
    if not isinstance(file_size, int) or file_size <= 0:
        raise serializers.ValidationError({field_name: f"{label} cannot be empty."})
    if isinstance(file_size, int) and file_size > max_size_mb * 1024 * 1024:
        raise serializers.ValidationError({field_name: f"{label} must be smaller than {max_size_mb} MB."})

    if allowed_content_types:
        content_type = str(getattr(uploaded_file, "content_type", "") or "").strip().lower()
        if not content_type:
            content_type = (mimetypes.guess_type(file_name)[0] or "").strip().lower()

        if content_type and content_type not in allowed_content_types:
            expected = ", ".join(sorted(allowed_content_types))
            raise serializers.ValidationError({field_name: f"{label} must be a valid {expected} file."})
