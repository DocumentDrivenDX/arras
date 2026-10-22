# SPDX-License-Identifier: MIT OR Apache-2.0
"""A small owner-only credential source for the local development host."""

from __future__ import annotations

import json
import os
import secrets
import stat
from pathlib import Path
from typing import Any, cast


class FileCredentialSource:
    """Read or atomically create role passwords in a private local file.

    Existing-role lookups never create an entry. Callers must opt into creation only after the
    database confirms that the corresponding role is absent.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(os.path.abspath(path.expanduser()))
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    def __call__(self, role: str, *, create: bool) -> str:
        if not create:
            try:
                self._check_path_components()
                self._validate_parent()
                token = self._read().get(role)
                if token:
                    return token
            except FileNotFoundError:
                raise ValueError("credential is missing") from None
            except Exception:
                raise ValueError("credential store is unsafe or malformed") from None
            raise ValueError("credential is missing") from None
        self._ensure_parent()
        try:
            self._check_path_components()
            fd = self._open_lock()
        except Exception:
            raise ValueError("credential store is unsafe or unavailable") from None
        try:
            with os.fdopen(fd, "r+b", closefd=True) as lock:
                import fcntl

                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                credentials = self._read()
                token = credentials.get(role)
                if token is not None:
                    return token
                token = secrets.token_urlsafe(32)
                credentials[role] = token
                self._write(credentials)
                return token
        except ValueError:
            raise ValueError(
                "credential store is unsafe, malformed, or missing the requested credential"
            ) from None
        except Exception:
            raise ValueError("credential store is unsafe or unavailable") from None

    def _ensure_parent(self) -> None:
        try:
            self._check_path_components()
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self._validate_parent()
            self._check_path_components()
        except Exception:
            raise ValueError("credential store directory is unsafe or unavailable") from None

    def _validate_parent(self) -> None:
        info = self.path.parent.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise ValueError

    def _check_path_components(self) -> None:
        current = Path(self.path.anchor)
        for part in self.path.parts[1:-1]:
            current /= part
            try:
                info = current.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode):
                raise ValueError

    def _open_lock(self) -> int:
        flags = os.O_RDWR | os.O_CREAT | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.lock_path, flags, 0o600)
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            os.close(fd)
            raise ValueError
        return fd

    def _read(self) -> dict[str, str]:
        try:
            flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(self.path, flags)
        except FileNotFoundError:
            return {}
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_size > 65_536
            ):
                raise ValueError
            payload = stream.read(65_537)
            if len(payload) > 65_536:
                raise ValueError
            raw: object = json.loads(payload, object_pairs_hook=self._unique_pairs)
        if not isinstance(raw, dict):
            raise ValueError
        envelope = cast(dict[str, Any], raw)
        if envelope.get("version") != 1:
            raise ValueError
        credentials = envelope.get("credentials")
        if not isinstance(credentials, dict) or any(
            not isinstance(key, str) or not isinstance(value, str) or not key or not value
            for key, value in cast(dict[Any, Any], credentials).items()
        ):
            raise ValueError
        return cast(dict[str, str], credentials)

    @staticmethod
    def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    def _write(self, credentials: dict[str, str]) -> None:
        payload = json.dumps(
            {"version": 1, "credentials": credentials},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        if len(payload) > 65_536:
            raise ValueError("credential store exceeds 64 KiB")
        temporary = self.path.with_name(f".{self.path.name}.{secrets.token_hex(8)}.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(fd, "wb", closefd=True) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


__all__ = ["FileCredentialSource"]
