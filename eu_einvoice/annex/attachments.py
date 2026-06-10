# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass

import frappe
from frappe import _
from frappe.core.doctype.file.utils import find_file_by_url


@dataclass(frozen=True)
class EInvoiceAnnexAttachment:
	file_id: str
	basename: str
	mime_type: str | None
	content: bytes | None
	issuer_assigned_id: str
	row_idx: int | None

	@classmethod
	def from_annex_row(cls, row) -> EInvoiceAnnexAttachment:
		return cls.from_file(frappe.get_doc("File", row.file), row_idx=row.idx)

	@classmethod
	def from_file(cls, file_doc, *, row_idx: int | None) -> EInvoiceAnnexAttachment:
		content = None
		basename = file_doc.file_name
		mime_type = None

		if not file_doc.is_remote_file:
			basename = os.path.basename(file_doc.file_url)
			mime_type = mimetypes.guess_type(file_doc.file_url)[0]
			content = file_doc.get_content()

		return cls(
			file_id=file_doc.name,
			basename=basename,
			mime_type=mime_type,
			content=content,
			issuer_assigned_id=file_doc.name,
			row_idx=row_idx,
		)

	@classmethod
	def from_legacy_url(cls, legacy_url: str) -> EInvoiceAnnexAttachment:
		file = find_file_by_url(legacy_url)
		if not file:
			frappe.throw(_("Annex file not found: {0}").format(legacy_url))

		return cls.from_file(file, row_idx=None)


def has_annex_attachments(doc) -> bool:
	if doc.doctype != "Sales Invoice":
		return False

	if is_multi_annex_embed_enabled():
		return len(doc.get("einvoice_annexes") or []) > 0

	return bool(doc.get("einvoice_embedded_document"))


def get_attachments_from_annex_table(doc) -> list[EInvoiceAnnexAttachment]:
	"""Get annex attachments from the annex table. Assumes multi-annex embed is enabled."""
	if doc.doctype != "Sales Invoice":
		frappe.throw(_("Annex attachments are only supported on Sales Invoice"))

	rows = doc.get("einvoice_annexes") or []

	attachments = []
	for row in sorted(rows, key=lambda row: row.idx):
		attachments.append(EInvoiceAnnexAttachment.from_annex_row(row))
	return attachments


def is_multi_annex_embed_enabled() -> bool:
	return bool(
		frappe.db.get_single_value("E Invoice Settings", "multi_annex_embed_enabled")
	)


def _attachments_from_legacy(legacy_url: str) -> list[EInvoiceAnnexAttachment]:
	file = find_file_by_url(legacy_url)
	if not file:
		frappe.throw(_("Annex file not found: {0}").format(legacy_url))

	_log_legacy_deprecation_once()
	return [EInvoiceAnnexAttachment.from_file(file, row_idx=None)]


def _log_legacy_deprecation_once() -> None:
	if frappe.flags.annex_legacy_deprecation_logged:
		return

	frappe.logger("eu_einvoice").warning(
		"Sales Invoice annex resolved from legacy field einvoice_embedded_document; "
		"enable Multi annex embed in E Invoice Settings for the annex table."
	)
	frappe.flags.annex_legacy_deprecation_logged = True
