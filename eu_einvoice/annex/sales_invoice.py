# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.core.doctype.file.utils import find_file_by_url


def migrate_embedded_document_to_annexes(doc) -> bool:
	"""Move a legacy ``einvoice_embedded_document`` value into ``einvoice_annexes``.

	Caller must enable multi-annex embed and ensure ``einvoice_embedded_document`` is set.

	Returns:
	    True when a legacy attachment was migrated.
	"""

	file = find_file_by_url(doc.einvoice_embedded_document)
	if not file:
		doc.einvoice_embedded_document = None
		return False

	doc.append("einvoice_annexes", {"file": file.name})
	doc.einvoice_embedded_document = None

	frappe.msgprint(
		_(
			"The embedded document was moved to the E-Invoice annex table. "
			"It will be embedded from the annex rows on submit."
		),
		alert=True,
		indicator="orange",
	)
	return True


def deduplicate_annex_rows(doc) -> None:
	"""Collapse duplicate annex ``file`` links; the last row for each file wins.

	Caller must enable multi-annex embed and ensure ``einvoice_annexes`` is non-empty.
	"""

	rows = doc.einvoice_annexes

	last_row_by_file: dict[str, object] = {}
	file_order: list[str] = []

	for row in rows:
		if row.file not in last_row_by_file:
			file_order.append(row.file)
		last_row_by_file[row.file] = row

	if len(file_order) == len(rows):
		# no duplicates to remove
		return

	doc.set("einvoice_annexes", [])
	for file_id in file_order:
		source = last_row_by_file[file_id]
		row_data = {
			"file": source.file,
			"display_name": source.display_name,
		}
		if source.get("file_name"):
			row_data["file_name"] = source.file_name
		doc.append("einvoice_annexes", row_data)

	removed_count = len(rows) - len(file_order)
	frappe.msgprint(
		_(
			"{0} duplicate annex row(s) were removed. "
			"The last row for each file was kept."
		).format(removed_count),
		alert=True,
		indicator="orange",
	)
