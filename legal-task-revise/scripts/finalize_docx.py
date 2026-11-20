#!/usr/bin/env python3
"""Set requested Word metadata without rewriting legal content or accepting revisions."""

import argparse
import json
import os
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from task_clock import stopped_minutes

AUTHOR = "Renat Sigunov"
NS = {
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}
for prefix in ("cp", "dc", "dcterms", "xsi", "ep"):
    ET.register_namespace(prefix, NS[prefix])
META = {"docProps/core.xml", "docProps/app.xml", "[Content_Types].xml", "_rels/.rels"}
CORE_TYPE = "application/vnd.openxmlformats-package.core-properties+xml"
APP_TYPE = "application/vnd.openxmlformats-officedocument.extended-properties+xml"
CORE_REL = "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
APP_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties"


def q(prefix, name):
    return "{" + NS[prefix] + "}" + name


def parse_xml(data):
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("DTD/entity declarations are not supported in DOCX XML")
    return ET.fromstring(data)


def xml_bytes(root):
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def set_text(root, tag, text):
    matches = root.findall(tag)
    node = matches[0] if matches else ET.SubElement(root, tag)
    for extra in matches[1:]:
        root.remove(extra)
    node.text = text
    return node


def markup_issues(parts):
    findings = set()
    hidden = set()
    has_revision = False
    revisions = {"ins", "del", "moveFrom", "moveTo", "cellIns", "cellDel",
                 "cellMerge", "numberingChange", "tblGridChange"}
    for name, data in parts.items():
        if not name.startswith("word/") or not name.endswith(".xml"):
            continue
        if Path(name).name.startswith("comments"):
            findings.add(name + ": comments part")
        root = parse_xml(data)
        for node in root.iter():
            if not node.tag.startswith("{" + NS["w"] + "}"):
                continue
            local = node.tag.split("}", 1)[1]
            revision = local in revisions or local.endswith("PrChange")
            if revision:
                has_revision = True
            if (revision or local in {"delText", "delInstrText"} or
                    local.startswith(("moveFromRange", "moveToRange", "customXmlInsRange", "customXmlDelRange",
                                      "customXmlMoveFromRange", "customXmlMoveToRange", "commentRange", "commentReference"))):
                findings.add(name + ": " + local)
            if local in {"trackRevisions", "vanish", "webHidden"}:
                if node.get(q("w", "val"), "true").lower() not in {"0", "false", "off"}:
                    finding = name + ": " + local
                    findings.add(finding)
                    if local != "trackRevisions":
                        hidden.add(finding)
    return sorted(findings), sorted(hidden), has_revision


def ensure_metadata_declarations(parts):
    types = parse_xml(parts["[Content_Types].xml"])
    rels = parse_xml(parts["_rels/.rels"])
    types_changed = rels_changed = False
    for path, content_type, rel_type in (("docProps/core.xml", CORE_TYPE, CORE_REL),
                                         ("docProps/app.xml", APP_TYPE, APP_REL)):
        existing = [n for n in types if n.get("PartName") == "/" + path]
        if not existing:
            ET.SubElement(types, q("ct", "Override"), {"PartName": "/" + path, "ContentType": content_type})
            types_changed = True
        elif len(existing) != 1 or existing[0].get("ContentType") != content_type:
            raise ValueError("Invalid metadata content type: " + path)
        links = [n for n in rels if n.get("Type") == rel_type]
        if links:
            if len(links) != 1 or links[0].get("Target", "").lstrip("/") != path or links[0].get("TargetMode") == "External":
                raise ValueError("Nonstandard metadata relationship requires manual inspection: " + path)
        else:
            ids = {n.get("Id") for n in rels}
            index = 1
            while f"rIdMetadata{index}" in ids:
                index += 1
            ET.SubElement(rels, q("rel", "Relationship"), {"Id": f"rIdMetadata{index}", "Type": rel_type, "Target": path})
            rels_changed = True
    if types_changed:
        parts["[Content_Types].xml"] = xml_bytes(types)
    if rels_changed:
        parts["_rels/.rels"] = xml_bytes(rels)


def finalize(source, output, clock, allow_source_markup=False, *, work_product_redline=False):
    if allow_source_markup and work_product_redline:
        raise ValueError("Choose either source markup or redline work-product finalization")
    if source.resolve() == output.resolve() or output.exists():
        raise ValueError("Use a new output path; sources and existing outputs are never overwritten")
    if source.suffix.lower() != ".docx" or output.suffix.lower() != ".docx":
        raise ValueError("Input and output must be .docx")
    minutes = stopped_minutes(clock)
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(n.casefold() for n in names)):
            raise ValueError("Duplicate DOCX package parts")
        if len(infos) > 10000 or sum(i.file_size for i in infos) > 250 * 1024 * 1024:
            raise ValueError("DOCX exceeds package limits")
        if any(n.lower().startswith("_xmlsignatures/") or "vbaproject" in n.lower() for n in names):
            raise ValueError("Signed or macro-bearing package requires separate handling")
        original = {info.filename: archive.read(info) for info in infos}
    if not {"word/document.xml", "[Content_Types].xml", "_rels/.rels"} <= original.keys():
        raise ValueError("Missing required DOCX package parts")
    content_types = parse_xml(original["[Content_Types].xml"])
    if any("macroenabled" in n.get("ContentType", "").lower() or "vbaproject" in n.get("ContentType", "").lower() for n in content_types):
        raise ValueError("Macro-enabled content types are not supported")
    findings, hidden, has_revision = markup_issues(original)
    if work_product_redline:
        if hidden:
            raise ValueError("Resolve hidden content before redline finalization: " + "; ".join(hidden[:12]))
        if not has_revision:
            raise ValueError("Redline work product must contain native Word revisions")
    elif findings and not allow_source_markup:
        raise ValueError("Resolve markup/hidden content before finalization: " + "; ".join(findings[:12]))
    parts = dict(original)
    core = parse_xml(parts["docProps/core.xml"]) if "docProps/core.xml" in parts else ET.Element(q("cp", "coreProperties"))
    app = parse_xml(parts["docProps/app.xml"]) if "docProps/app.xml" in parts else ET.Element(q("ep", "Properties"))
    if core.tag != q("cp", "coreProperties") or app.tag != q("ep", "Properties"):
        raise ValueError("Unexpected metadata namespace/root")
    set_text(core, q("dc", "creator"), AUTHOR)
    set_text(core, q("cp", "lastModifiedBy"), AUTHOR)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    set_text(core, q("dcterms", "modified"), timestamp).set(q("xsi", "type"), "dcterms:W3CDTF")
    if core.find(q("dcterms", "created")) is None:
        set_text(core, q("dcterms", "created"), timestamp).set(q("xsi", "type"), "dcterms:W3CDTF")
    removed = []
    for root, tag in ((core, q("dc", "description")), (app, q("ep", "Application"))):
        for node in list(root.findall(tag)):
            if (node.text or "").strip().lower() in {"generated by python-docx", "python-docx", "python docx", "openai", "chatgpt", "codex"}:
                root.remove(node)
                removed.append(tag)
    set_text(app, q("ep", "TotalTime"), str(minutes))
    parts["docProps/core.xml"] = xml_bytes(core)
    parts["docProps/app.xml"] = xml_bytes(app)
    ensure_metadata_declarations(parts)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".finalize-", suffix=".docx", dir=output.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for info in infos:
                archive.writestr(info, parts[info.filename])
            for name in parts.keys() - original.keys():
                archive.writestr(name, parts[name])
        with zipfile.ZipFile(tmp) as archive:
            if archive.testzip():
                raise ValueError("Output failed ZIP integrity check")
            for name, data in original.items():
                if name not in META and archive.read(name) != data:
                    raise ValueError("Unexpected document-content modification: " + name)
            final_core = parse_xml(archive.read("docProps/core.xml"))
            final_app = parse_xml(archive.read("docProps/app.xml"))
            if (final_core.findtext(q("dc", "creator")) != AUTHOR or
                    final_core.findtext(q("cp", "lastModifiedBy")) != AUTHOR or
                    final_app.findtext(q("ep", "TotalTime")) != str(minutes)):
                raise ValueError("Final metadata verification failed")
        # Hard-link creation is atomic and refuses an existing output.
        os.link(tmp, output)
    finally:
        tmp.unlink(missing_ok=True)
    markup_field = "preserved_redline_markup" if work_product_redline else "preserved_source_markup"
    return {"output": str(output.resolve()), "author": AUTHOR, "word_minutes": minutes,
            "modified": timestamp, "content_parts_unchanged": True,
            markup_field: findings, "removed_generator_defaults": removed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--clock", required=True, type=Path)
    markup = parser.add_mutually_exclusive_group()
    markup.add_argument("--allow-source-markup", action="store_true")
    markup.add_argument("--work-product-redline", action="store_true")
    args = parser.parse_args()
    try:
        result = finalize(args.input, args.output, args.clock, args.allow_source_markup,
                          work_product_redline=args.work_product_redline)
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError, zipfile.BadZipFile, RuntimeError) as exc:
        parser.exit(1, f"error: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
