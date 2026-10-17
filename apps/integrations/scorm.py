"""SCORM 1.2 / 2004 package handling: safe extraction, manifest parsing, attempt data."""
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from django.conf import settings

MAX_UNPACKED = 500 * 1024 * 1024


def extract(pkg):
    """Unzip into media/scorm/<id>/ (zip-slip safe) and find the launch file from imsmanifest.xml."""
    dest = Path(settings.MEDIA_ROOT) / "scorm" / str(pkg.pk)
    dest.mkdir(parents=True, exist_ok=True)
    total = 0
    with zipfile.ZipFile(pkg.package.path) as z:
        for info in z.infolist():
            target = (dest / info.filename).resolve()
            if not str(target).startswith(str(dest.resolve())):
                raise ValueError("Unsafe path in package")
            total += info.file_size
            if total > MAX_UNPACKED:
                raise ValueError("Package too large when unpacked")
        z.extractall(dest)
    manifest = dest / "imsmanifest.xml"
    if not manifest.exists():
        raise ValueError("imsmanifest.xml not found: is this a SCORM package?")
    tree = ElementTree.parse(manifest)
    ns = {"": tree.getroot().tag.split("}")[0].strip("{")} if "}" in tree.getroot().tag else {}
    text = manifest.read_text(encoding="utf-8", errors="ignore")
    version = "2004" if "2004" in text or "adlcp_v1p3" in text else "1.2"
    href = ""
    for res in tree.getroot().iter():
        if res.tag.endswith("resource") and res.get("href"):
            href = res.get("href")
            break
    title_el = next((e for e in tree.getroot().iter() if e.tag.endswith("title") and (e.text or "").strip()), None)
    pkg.launch_path = href
    pkg.version = version
    pkg.extracted_dir = f"scorm/{pkg.pk}"
    pkg.title = title_el.text.strip() if title_el is not None else ""
    pkg.save()
    return pkg


COMPLETE_STATUSES = {"completed", "passed"}


def is_complete(cmi, version):
    if version == "2004":
        return cmi.get("cmi.completion_status") == "completed" or cmi.get("cmi.success_status") == "passed"
    return cmi.get("cmi.core.lesson_status") in COMPLETE_STATUSES
