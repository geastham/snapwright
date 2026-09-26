"""Embed Pillow images in a reportlab PDF as indexed-colour (palette) images.

reportlab expands palette images to 24-bit RGB before compressing them, in slow Python, and
wraps them in ASCII85. Our renders are flat illustrations with a few dozen colours, so we
quantise them (to the renderer's exact colours when given) and write a PDF /Indexed image
with Flate compression ourselves: a fraction of the size, and much faster to write.
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
    def __init__(self, name, pil_rgb, colors=48, palette=None):
        if palette is not None and len(palette) <= 256:
            # the renderer's exact colours: every pixel maps to one of them, so no colour is
            # lost however rare (an adaptive palette can merge a small dark-blue window into grey)
            pimg = Image.new("P", (1, 1))
            flat = [c for rgb in palette for c in rgb]
            pimg.putpalette(flat + flat[:3] * (256 - len(palette)))
            q = pil_rgb.convert("RGB").quantize(palette=pimg, dither=Image.Dither.NONE)
            colors = len(palette)
        else:
            # fast octree: 10x faster than median cut here, no visible difference on renders
            q = pil_rgb.convert("RGB").quantize(colors, method=Image.Quantize.FASTOCTREE, dither=0)
        pal = q.getpalette()[: 3 * colors]
        idx = np.asarray(q, dtype=np.uint8)
        self.name = name
        self.height, self.width = idx.shape
        self.ncolors = len(pal) // 3
        # plain Flate: on palette indices a PNG predictor makes things bigger (tested: +20%)
        self.stream = zlib.compress(idx.tobytes(), 6)
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
        d["Length"] = len(self.stream)
        return S.format(document)


def draw_indexed(c, pil_rgb, x, y, width, height, colors=48, preserveAspectRatio=False, anchor="c",
                 palette=None):
    """Like canvas.drawImage for a Pillow image, but embedded as an indexed-colour image
    (with `palette`, a list of RGB tuples, as its exact colours). Identical images are stored
    once."""
    raw = pil_rgb.convert("RGB").tobytes()
    name = "ix" + hashlib.md5(raw + bytes([colors]) + str(pil_rgb.size).encode()
                              + str(len(palette or ())).encode()).hexdigest()
    reg = c._doc.getXObjectName(name)
    obj = c._doc.idToObject.get(reg)
    if obj is None:
        obj = IndexedImage(name, pil_rgb, colors, palette)
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
