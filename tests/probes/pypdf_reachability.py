"""Does bid-deadline-check's PDF text path reach pypdf's image conversion (GHSA-5hx5-vpf9-5wcv: _xobj_to_image passed
/DCTDecode data to Pillow's Image.open without a format restriction)? Builds a synthetic PDF whose page draws an image
XObject labelled /DCTDecode (bytes that are not JPEG) and holds an inline /DCT image, then runs the tool's own text
extraction with a spy on _xobj_to_image and a stand-in PIL module that records Image.open. A count of 0 shows the
path is not reached for this file; it does not prove that no PDF can reach it.
Usage: python3 -I pypdf_reachability.py <bid src dir> <work dir>"""
import json, sys, types
from pathlib import Path
src, work = sys.argv[1], Path(sys.argv[2]); sys.path.insert(0, src)
calls = {"xobj_to_image": 0, "Image.open": 0}
# Without Pillow, pypdf's image module does not import at all; the stand-in lets the code path be traced as if it were
# installed. Its open() records the call and refuses, so no image parser ever runs.
def _open(*a, **k):
    calls["Image.open"] += 1
    raise OSError("stand-in Image.open")
fake_image = types.ModuleType("PIL.Image"); fake_image.open = _open; fake_image.Image = type("Image", (), {})
fake_pil = types.ModuleType("PIL"); fake_pil.Image = fake_image; fake_pil.__version__ = "stand-in"
fake_pil.UnidentifiedImageError = type("UnidentifiedImageError", (OSError,), {})
sys.modules["PIL"] = fake_pil; sys.modules["PIL.Image"] = fake_image
import pypdf, pypdf.generic._image_xobject as ix
real = ix._xobj_to_image
def spy(*a, **k):
    calls["xobj_to_image"] += 1
    return real(*a, **k)
ix._xobj_to_image = spy
not_jpeg = b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 1 1\nshowpage\n"  # never executed: no Ghostscript call is made
content = (b"BT /F1 12 Tf 72 720 Td (Proposals due November 5, 2026 at 5:00 PM ET.) Tj ET\n"
           b"q 10 0 0 10 72 600 cm /Im1 Do Q\n"
           # Inline /DCT data is read by pypdf's own marker reader during text extraction, which needs a JPEG frame
           # (SOI, a comment segment carrying the non-JPEG bytes, EOI) to find where the image ends.
           b"BI /W 1 /H 1 /CS /G /BPC 8 /F /DCT ID " + b"\xff\xd8\xff\xfe" + (len(not_jpeg) + 2).to_bytes(2, "big") + not_jpeg + b"\xff\xd9" + b" EI\n")
objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> /XObject << /Im1 6 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n" % len(not_jpeg) + not_jpeg + b"\nendstream"]
out = bytearray(b"%PDF-1.7\n"); offs = []
for i, o in enumerate(objs, 1):
    offs.append(len(out)); out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
x = len(out); out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)
work.mkdir(parents=True, exist_ok=True); pdf = work / "dct-not-jpeg.pdf"; pdf.write_bytes(bytes(out))
from bid_deadline_check import core
text = core._bounded_pdf_text(pypdf.PdfReader(str(pdf)))
res = {"pypdf": pypdf.__version__, "text_found": "November 5, 2026" in text, "calls_during_text_extraction": dict(calls)}
try:  # control: the image API on the same page does reach it
    pypdf.PdfReader(str(pdf)).pages[0].images[0].image
except Exception as e:
    res["control_error"] = type(e).__name__
res["calls_after_images_control"] = dict(calls)
print(json.dumps(res))
