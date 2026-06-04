# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""XRechnung §8.2 MIME allowlist for user-selected e-invoice annex files."""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import frappe
from frappe import _
from filetype import guess_mime

ANNEX_FORBIDDEN_MIME_TYPES: frozenset[str] = frozenset({"application/xml", "text/xml"})

# Expected content MIME per file suffix when validating file bytes (XRechnung §8.2 user annexes).
EXTENSION_CONTENT_MIMES: dict[str, str] = {
	".pdf": "application/pdf",
	".png": "image/png",
	".jpg": "image/jpeg",
	".jpeg": "image/jpeg",
	".csv": "text/csv",
	".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
	".ods": "application/vnd.oasis.opendocument.spreadsheet",
}

# Max bytes read from annex content for CSV text sniffing (null-byte and decode checks).
_CONTENT_SNIFF_LIMIT = 8192


def get_annex_allowed_extensions() -> frozenset[str]:
	"""Return allowed annex file suffixes (XRechnung §8.2 user annexes)."""
	return frozenset(EXTENSION_CONTENT_MIMES.keys())


def get_annex_allowed_mime_types() -> frozenset[str]:
	"""Return allowed annex MIME types derived from ``EXTENSION_CONTENT_MIMES``."""
	return frozenset(EXTENSION_CONTENT_MIMES.values())


@frappe.whitelist()
def get_annex_allowed_extensions_text() -> str:
	"""Return comma-separated allowed annex suffixes for Desk display (same as server error messages)."""
	return ", ".join(sorted(get_annex_allowed_extensions()))


def get_extension(file_name: str) -> str:
	"""Return the lowercase file suffix including the leading dot."""
	return Path(file_name).suffix.lower()


def is_annex_extension_allowed(file_name: str) -> bool:
	"""Return whether *file_name* has suffix on the allowlist."""
	return get_extension(file_name) in get_annex_allowed_extensions()


@frappe.whitelist()
def is_annex_extension_allowed_for_file_id(file_id: str) -> bool:
	"""Desk: return whether the linked **File** has an allowed annex extension.

	Params:
	    file_id: **File** name (database id) linked from **E Invoice Annex Row** ``file``.

	Returns:
	    ``True`` when the file name extension is allowed; ``False`` otherwise.
	"""
	file_name = frappe.db.get_value("File", file_id, "file_name")
	if not file_name:
		return False
	return is_annex_extension_allowed(file_name)


def annex_validation_by_content_enabled() -> bool:
	"""Return whether annex files must match the allowlist by file content."""
	return bool(
		frappe.db.get_single_value(
			"E Invoice Settings",
			"annex_validation_by_content_enabled",
		)
	)


def _looks_like_text_csv(content: bytes) -> bool:
	sample = content[:_CONTENT_SNIFF_LIMIT]
	if b"\x00" in sample:
		return False  # binary data is not CSV text
	for encoding in ("utf-8", "latin-1"):
		try:
			sample.decode(encoding)
			return True
		except UnicodeDecodeError:
			continue
	return False


def _detect_spreadsheet_zip_mime(content: bytes) -> str | None:
	try:
		with zipfile.ZipFile(BytesIO(content)) as archive:
			names = archive.namelist()
			if "mimetype" in names:
				mimetype = archive.read("mimetype").decode("utf-8", errors="ignore").strip()
				if mimetype == "application/vnd.oasis.opendocument.spreadsheet":
					return mimetype  # ODF packages declare MIME in mimetype
			if any(name.startswith("xl/") for name in names):
				return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"  # OOXML uses xl/ prefix
	except (zipfile.BadZipFile, OSError, ValueError):
		frappe.log_error(
			title=_("E-Invoice annex spreadsheet zip sniff failed"),
			message=frappe.get_traceback(),
		)
		


def detect_annex_mime_from_content(content: bytes, *, file_name: str | None = None) -> str | None:
	"""Detect MIME type from file bytes (magic numbers and format-specific checks).

	Params:
	    content: Raw file bytes.
	    file_name: Optional file name used for CSV text fallback and zip refinement.

	Returns:
	    Detected MIME type, or ``None`` when the type cannot be determined.
	"""
	# filetype has no XML matcher; also blocks XML posing as CSV text
	stripped = content.lstrip()
	if stripped.startswith((b"<?xml", b"<")):
		return "application/xml"

	mime_type = guess_mime(content)
	if mime_type == "application/zip":
		# xlsx and ods both sniff as generic zip
		spreadsheet_mime = _detect_spreadsheet_zip_mime(content)
		if spreadsheet_mime:
			return spreadsheet_mime

	if mime_type is None and file_name and get_extension(file_name) == ".csv":
		if _looks_like_text_csv(content):
			# CSV has no magic bytes; accept decodable text when suffix is .csv
			return "text/csv"

	return mime_type


def content_mime_matches_extension(content_mime: str, suffix: str) -> bool:
	"""Return whether detected content MIME matches the expected type for *suffix*."""
	expected = EXTENSION_CONTENT_MIMES.get(suffix)
	if not expected:
		return False
	return content_mime == expected


def _validate_annex_file_content(
	file_id: str, file_name: str, *, row_index: int | None = None
) -> None:
	content = frappe.get_doc("File", file_id).get_content()
	if not content:
		frappe.throw(_("E-Invoice annex file {0} is empty.").format(file_name))

	content_mime = detect_annex_mime_from_content(content, file_name=file_name)
	suffix = get_extension(file_name)

	if content_mime in ANNEX_FORBIDDEN_MIME_TYPES:
		_throw_annex_extension_not_allowed(row_index=row_index)  # user annexes must not include custom XML

	if not content_mime or content_mime not in get_annex_allowed_mime_types():
		_throw_annex_extension_not_allowed(row_index=row_index)  # unknown or disallowed bytes

	if suffix and not content_mime_matches_extension(content_mime, suffix):
		_throw_annex_extension_not_allowed(row_index=row_index)  # mislabelled extension vs content


def validate_annex_file(
	file_id: str, *, row_index: int | None = None, validate_by_content: bool | None = None
) -> None:
	"""Validate that a linked **File** is an allowed user annex type.

	Extension checks always run. Content checks run only when
	**E Invoice Settings** ``annex_validation_by_content_enabled`` is set, unless
	*validate_by_content* is passed explicitly (e.g. in tests).

	Params:
	    file_id: **File** name linked from **E Invoice Annex Row** ``file``.
	    row_index: Optional child-table row number for error messages.
	    validate_by_content: Override settings; ``None`` reads **E Invoice Settings**.

	Raises:
	    frappe.ValidationError: When the file is missing or its MIME type is not allowed.
	"""
	file_name = frappe.db.get_value("File", file_id, "file_name")
	if not file_name:
		frappe.throw(_("Attached file {0} was not found.").format(file_id))

	if not is_annex_extension_allowed(file_name):
		_throw_annex_extension_not_allowed(row_index=row_index)
		return

	if validate_by_content is None:
		validate_by_content = annex_validation_by_content_enabled()
	if validate_by_content:
		_validate_annex_file_content(file_id, file_name, row_index=row_index)  # optional; reads file bytes


def _throw_annex_extension_not_allowed(*, row_index: int | None = None) -> None:
	row_label = ""
	if row_index is not None:
		row_label = _(" (row {0})").format(row_index)
	frappe.throw(
		_("E-Invoice annex{row}: allowed file extensions: {allowed}.").format(
			row=row_label,
			allowed=get_annex_allowed_extensions_text(),
		)
	)


def validate_sales_invoice_annex_files(doc) -> None:
	"""Validate all **E Invoice Annex Row** files on a **Sales Invoice** before save.

	Params:
	    doc: **Sales Invoice** document (or dict with ``einvoice_annexes`` child rows).

	Raises:
	    frappe.ValidationError: When any linked annex file fails ``validate_annex_file``.
	"""
	rows = doc.get("einvoice_annexes") or []
	for row in rows:
		if not row.file:
			continue
		validate_annex_file(row.file, row_index=row.idx)
