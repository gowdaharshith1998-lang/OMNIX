"""PIC and COMP-3 helpers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PicSpec:
    kind: str
    digits: int
    signed: bool
    scale: int = 0


def parse_pic(pic: str) -> PicSpec:
    up = pic.upper().replace(" ", "")
    signed = up.startswith("S")
    if signed:
        up = up[1:]
    up = up.replace("COMP-3", "")
    if "V" in up:
        left, right = up.split("V", 1)
        if left.startswith("9(") and ")" in left:
            left_digits = int(left.split("9(", 1)[1].split(")", 1)[0])
        elif left.startswith("9"):
            left_digits = left.count("9")
        else:
            raise ValueError(f"unsupported PIC: {pic}")
        if right.startswith("9(") and right.endswith(")"):
            scale = int(right.split("9(", 1)[1][:-1])
        else:
            scale = right.count("9")
        return PicSpec(kind="numeric", digits=left_digits + scale, signed=signed, scale=scale)
    if "9(" in up and up.endswith(")"):
        digits = int(up.split("9(", 1)[1][:-1])
        return PicSpec(kind="numeric", digits=digits, signed=signed)
    if up.startswith("X(") and up.endswith(")"):
        return PicSpec(kind="alpha", digits=int(up[2:-1]), signed=False)
    if "$" in up or "," in up or "-" in up:
        digits = up.count("9") + up.count("Z")
        scale = len(up.rsplit(".", 1)[1].replace("-", "")) if "." in up else 0
        return PicSpec(kind="edited", digits=digits, signed="-" in up, scale=scale)
    raise ValueError(f"unsupported PIC: {pic}")


def decode_comp3(raw: bytes, *, digits: int, signed: bool, scale: int = 0) -> Decimal:
    if not raw:
        return Decimal(0)
    nibbles: list[int] = []
    for b in raw:
        nibbles.append((b >> 4) & 0x0F)
        nibbles.append(b & 0x0F)
    sign_nibble = nibbles.pop()
    body = nibbles[-digits:]
    num = int("".join(str(d) for d in body)) if body else 0
    neg = sign_nibble == 0x0D and signed
    value = Decimal(-num if neg else num)
    return value.scaleb(-scale) if scale else value


def encode_comp3(value: int | Decimal, *, digits: int, signed: bool, scale: int = 0) -> bytes:
    quantized = int((Decimal(value).scaleb(scale)).to_integral_value()) if scale else int(value)
    neg = quantized < 0
    abs_s = str(abs(quantized)).rjust(digits, "0")[-digits:]
    nibbles = [int(ch) for ch in abs_s]
    sign_n = 0x0D if (signed and neg) else (0x0C if signed else 0x0F)
    nibbles.append(sign_n)
    if len(nibbles) % 2 != 0:
        nibbles.insert(0, 0)
    out = bytearray()
    for i in range(0, len(nibbles), 2):
        out.append((nibbles[i] << 4) | nibbles[i + 1])
    return bytes(out)


def validate_pic_boundary(value: int, *, digits: int, signed: bool) -> bool:
    if signed:
        lo = -(10**digits - 1)
        hi = 10**digits - 1
    else:
        lo = 0
        hi = 10**digits - 1
    return lo <= value <= hi
