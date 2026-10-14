"""Current-user Windows DPAPI. Only ciphertext is persisted."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import tempfile


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def transform(data, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("Windows DPAPI required")
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    incoming = Blob(len(data), buffer)
    outgoing = Blob()
    try:
        # UI_FORBIDDEN=1, never LOCAL_MACHINE: bound to this Windows user.
        if not function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
            raise RuntimeError("DPAPI operation failed")
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        ctypes.memset(buffer, 0, len(data))
        if outgoing.data:
            ctypes.memset(outgoing.data, 0, outgoing.size)
            kernel.LocalFree(outgoing.data)


class CredentialStore:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else Path(os.environ["LOCALAPPDATA"]) / "SmartTray" / "credentials"

    def path(self, device_id):
        return self.directory / (hashlib.sha256(device_id.encode()).hexdigest() + ".dpapi")

    def save(self, device_id, key):
        if not isinstance(key, str) or len(key.encode("latin1")) != 16:
            raise ValueError("Invalid Local_Key format")
        payload = json.dumps({"id": device_id, "key": key}).encode()
        encrypted = transform(payload)
        self.directory.mkdir(parents=True, exist_ok=True)
        # Temporary file contains ciphertext only; atomic replacement.
        fd, temporary = tempfile.mkstemp(dir=self.directory, suffix=".dpapi")
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(encrypted)
            os.replace(temporary, self.path(device_id))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def load(self, device_id):
        path = self.path(device_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(transform(path.read_bytes(), decrypt=True))
            if payload["id"] != device_id:
                raise ValueError
            return payload["key"]
        except Exception:
            raise RuntimeError("Credential unavailable or corrupted") from None
