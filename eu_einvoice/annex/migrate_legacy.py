# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _

from eu_einvoice.annex.sales_invoice import migrate_embedded_document_to_annexes


def migrate_all_legacy_embedded_documents() -> None:
	"""Move legacy ``einvoice_embedded_document`` values into annex rows site-wide."""
	invoices = frappe.get_all(
		"Sales Invoice",
		filters={"einvoice_embedded_document": ["!=", ""]},
		pluck="name",
	)

	for index, invoice_name in enumerate(invoices, start=1):
		doc = frappe.get_doc("Sales Invoice", invoice_name)
		try:
			if migrate_embedded_document_to_annexes(doc, msgprint=False):
				doc.save(ignore_permissions=True)
		except frappe.ValidationError:
			frappe.log_error(
				title=_("Legacy annex migration failed for {0}").format(invoice_name),
				message=frappe.get_traceback(),
			)

		if index % 100 == 0:
			frappe.db.commit()

	frappe.db.commit()
