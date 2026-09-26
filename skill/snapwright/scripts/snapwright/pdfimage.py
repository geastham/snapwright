"""Embed Pillow images in a reportlab PDF as indexed-colour (palette) images.

reportlab expands palette images to 24-bit RGB before compressing them, in slow Python, and
wraps them in ASCII85. Our renders are flat illustrations with a few dozen colours, so we
quantise them and write a PDF /Indexed image with Flate compression and the PNG "Up"
predictor ourselves: about a third of the size, and much faster to write.
"""
from __future__ import annotations

import hashlib
import zlib

import numpy as np
from PIL import Image
from reportlab.lib.boxstuff import aspectRatioFix
from reportlab.pdfbase.pdfdoc import PDFArray, PDFName, PDFObject, PDFStream


class _Raw(PDFObject):
    def __init__(self, data: bytes):
        self.data = data

    def format(self, document):
        return self.data


class IndexedImage(PDFObject):
    def __init__(self, name, pil_rgb, colors=48):
        # fast octree: 10x faster than median cut here, and no visible difference on renders
        q = pil_rgb.convert("RGB").quantize(colors, method=Image.Quantize.FASTOCTREE, dither=0)
        pal = q.getpalette()[: 3 * colors]
        idx = np.asarray(q, dtype=np.uint8)
        self.name = name
        self.height, self.width = idx.shape
        self.ncolors = len(pal) // 3
        # PNG "Up" predictor: each row stored as the byte difference to the row above
        up = idx.copy()
        up[1:] = idx[1:] - idx[:-1]
        rows = np.concatenate([np.full((self.height, 1), 2, np.uint8), up], axis=1)
        self.stream = zlib.compress(rows.tobytes(), 6)
        self.palette_hex = bytes(pal).hex().upper().encode()

    def format(self, document):
        S = PDFStream(content=self.stream)
        S.filters = []            # already Flate-compressed, keep it binary
        d = S.dictionary
        d["Type"] = PDFName("XObject")
        d["Subtype"] = PDFName("Image")
        d["Width"] = self.width
        d["Height"] = self.height
        d["BitsPerComponent"] = 8
        d["ColorSpace"] = PDFArray([PDFName("Indexed"), PDFName("DeviceRGB"), self.ncolors - 1,
                                    _Raw(b"<" + self.palette_hex + b">")])
        d["Filter"] = PDFName("FlateDecode")
        d["DecodeParms"] = _Raw(b"<< /Predictor 12 /Colors 1 /BitsPerComponent 8 /Columns %d >>"
                                % self.width)
        d["Length"] = len(self.stream)
        return S.format(document)


def draw_indexed(c, pil_rgb, x, y, width, height, colors=48, preserveAspectRatio=False, anchor="c"):
    """Like canvas.drawImage for a Pillow image, but embedded as an indexed-colour image.
    Identical images are stored once."""
    raw = pil_rgb.convert("RGB").tobytes()
    name = "ix" + hashlib.md5(raw + bytes([colors]) + str(pil_rgb.size).encode()).hexdigest()
    reg = c._doc.getXObjectName(name)
    obj = c._doc.idToObject.get(reg)
    if obj is None:
        obj = IndexedImage(name, pil_rgb, colors)
        c._setXObjects(obj)
        c._doc.Reference(obj, reg)
        c._doc.addForm(name, obj)
    x, y, width, height, _ = aspectRatioFix(preserveAspectRatio, anchor, x, y, width, height,
                                            obj.width, obj.height)
    c.saveState()
    c.translate(x, y)
    c.scale(width, height)
    c._code.append("/%s Do" % reg)
    c.restoreState()
    c._formsinuse.append(name)
    return obj.width, obj.height
