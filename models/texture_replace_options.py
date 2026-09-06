"""Texture2D replace options: format, mipmaps, and sampler settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DESTINATION_FORMAT_LABEL = "Use destination format"

TEXTURE_FORMAT_CHOICES: tuple[tuple[str, int | None], ...] = (
    (DESTINATION_FORMAT_LABEL, None),
    ("Alpha8", 1),
    ("RGB24", 3),
    ("RGBA32", 4),
    ("ARGB32", 5),
    ("BGRA32", 14),
    ("DXT1", 10),
    ("DXT5", 12),
    ("BC4", 26),
    ("BC5", 27),
    ("BC7", 25),
    ("ETC2_RGB", 45),
    ("ETC2_RGBA8", 47),
    ("ASTC_RGB_4x4", 48),
    ("ASTC_RGB_5x5", 49),
    ("ASTC_RGB_6x6", 50),
    ("ASTC_RGB_8x8", 51),
    ("ASTC_RGB_10x10", 52),
    ("ASTC_RGB_12x12", 53),
    ("ASTC_RGBA_4x4", 54),
    ("ASTC_RGBA_5x5", 55),
    ("ASTC_RGBA_6x6", 56),
    ("ASTC_RGBA_8x8", 57),
    ("ASTC_RGBA_10x10", 58),
    ("ASTC_RGBA_12x12", 59),
)

FILTER_MODE_LABELS = ("Point", "Bilinear", "Trilinear")
WRAP_MODE_LABELS = ("Repeat", "Clamp", "Mirror", "MirrorOnce")
COLOR_SPACE_LABELS = ("Gamma", "Linear")


def mipmap_count_for(
    width: int, height: int, *, has_mip_maps: bool, stored_count: int
) -> int:
    if not has_mip_maps:
        return 1
    if stored_count > 1:
        return stored_count
    count = 1
    current_w, current_h = width, height
    while current_w // 2 >= 4 and current_h // 2 >= 4:
        current_w //= 2
        current_h //= 2
        count += 1
    return count


def _as_int(value: object, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class TextureReplaceOptions:
    target_format: int | None = None
    has_mip_maps: bool = False
    mipmap_count: int = 1
    filter_mode: int = 1
    aniso: int = 1
    mip_bias: float = 0.0
    wrap_u: int = 1
    wrap_v: int = 1
    lightmap_format: int = 0
    color_space: int | None = None

    @classmethod
    def from_texture(cls, data: Any) -> TextureReplaceOptions:
        mip_count = _as_int(getattr(data, "m_MipCount", 1), 1)
        mip_flag = getattr(data, "m_MipMap", None)
        if mip_flag is None:
            has_mips = mip_count > 1
        else:
            has_mips = bool(mip_flag)
        if mip_count <= 0:
            mip_count = 2 if has_mips else 1

        settings = getattr(data, "m_TextureSettings", None)
        filter_mode = 1
        aniso = 1
        mip_bias = 0.0
        wrap_u = 1
        wrap_v = 1
        if settings is not None:
            filter_mode = _as_int(getattr(settings, "m_FilterMode", 1), 1)
            aniso = _as_int(getattr(settings, "m_Aniso", 1), 1)
            mip_bias = _as_float(getattr(settings, "m_MipBias", 0.0), 0.0)
            wrap_mode = getattr(settings, "m_WrapMode", None)
            wrap_u_val = getattr(settings, "m_WrapU", None)
            wrap_v_val = getattr(settings, "m_WrapV", None)
            default_wrap = _as_int(wrap_mode, 1) if wrap_mode is not None else 1
            wrap_u = default_wrap if wrap_u_val is None else _as_int(wrap_u_val, 1)
            wrap_v = default_wrap if wrap_v_val is None else _as_int(wrap_v_val, 1)

        color_space = getattr(data, "m_ColorSpace", None)
        if color_space is not None:
            color_space = _as_int(color_space, 0)

        return cls(
            target_format=None,
            has_mip_maps=has_mips,
            mipmap_count=mip_count,
            filter_mode=filter_mode,
            aniso=aniso,
            mip_bias=mip_bias,
            wrap_u=wrap_u,
            wrap_v=wrap_v,
            lightmap_format=_as_int(getattr(data, "m_LightmapFormat", 0), 0),
            color_space=color_space,
        )

    def resolve_target_format(self, data: Any) -> int:
        if self.target_format is not None:
            return self.target_format
        return _as_int(getattr(data, "m_TextureFormat", 4), 4)

    def apply_settings(self, data: Any) -> None:
        settings = getattr(data, "m_TextureSettings", None)
        if settings is not None:
            if hasattr(settings, "m_FilterMode"):
                settings.m_FilterMode = self.filter_mode
            if hasattr(settings, "m_Aniso"):
                settings.m_Aniso = self.aniso
            if hasattr(settings, "m_MipBias"):
                settings.m_MipBias = self.mip_bias
            if hasattr(settings, "m_WrapU"):
                settings.m_WrapU = self.wrap_u
            if hasattr(settings, "m_WrapV"):
                settings.m_WrapV = self.wrap_v
            if getattr(settings, "m_WrapMode", None) is not None:
                settings.m_WrapMode = self.wrap_u
        if hasattr(data, "m_LightmapFormat"):
            data.m_LightmapFormat = self.lightmap_format
        if (
            self.color_space is not None
            and getattr(data, "m_ColorSpace", None) is not None
        ):
            data.m_ColorSpace = self.color_space
