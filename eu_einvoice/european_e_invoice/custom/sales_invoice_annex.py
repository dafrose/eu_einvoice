# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from eu_einvoice.annex.validation import (
	get_annex_allowed_extensions_text,
)

SALES_INVOICE_ANNEX_TABLE_FIELD = "einvoice_annexes"
E_INVOICE_ANNEX_ROW_DOCTYPE = "E Invoice Annex Row"


def sales_invoice_annex_table_installed() -> bool:
	return bool(
		frappe.db.exists(
			"Custom Field",
			{"dt": "Sales Invoice", "fieldname": SALES_INVOICE_ANNEX_TABLE_FIELD},
		)
	)


def get_sales_invoice_annex_table_field_description() -> str:
	return _(
		"Add attachment files to embed into sales invoice PDF and/or XML. "
		"Allowed extensions: {extensions}. "
		"<br><b>Print format example:</b><br>"
		"<pre>{{% if doc.einvoice_annexes %}}"
		"{{% for row in doc.einvoice_annexes %}}"
		"&lt;p&gt;{{{{ row.display_name }}}}&lt;/p&gt;"
		"{{% endfor %}}"
		"{{% endif %}}</pre>"
	).format(extensions=get_annex_allowed_extensions_text())


def get_sales_invoice_annex_custom_fields() -> dict:
	return {
		"Sales Invoice": [
			{
				"fieldname": SALES_INVOICE_ANNEX_TABLE_FIELD,
				"label": _("E-Invoice Annexes"),
				"fieldtype": "Table",
				"options": E_INVOICE_ANNEX_ROW_DOCTYPE,
				"insert_after": "einvoice_embedded_document",
				"hidden": 0,
				"description": get_sales_invoice_annex_table_field_description(),
			},
		],
	}


def sync_sales_invoice_annex_field(enabled: bool) -> None:
	"""Create the annex table custom field when enabled, or toggle visibility when it exists."""
	if enabled:
		if sales_invoice_annex_table_installed():
			_set_sales_invoice_annex_field_hidden(hidden=False)
		else:
			_create_sales_invoice_annex_field()
	else:
		_set_sales_invoice_annex_field_hidden(hidden=True)


def _create_sales_invoice_annex_field() -> None:
	if not frappe.db.exists("DocType", E_INVOICE_ANNEX_ROW_DOCTYPE):
		frappe.throw(
			_(
				"DocType {0} is not installed. Run bench migrate for app european e-Invoice, then try again."
			).format(E_INVOICE_ANNEX_ROW_DOCTYPE)
		)

	create_custom_fields(get_sales_invoice_annex_custom_fields())
	frappe.clear_cache(doctype="Sales Invoice")


def _set_sales_invoice_annex_field_hidden(*, hidden: bool) -> None:
	custom_field_name = frappe.db.get_value(
		"Custom Field",
		{"dt": "Sales Invoice", "fieldname": SALES_INVOICE_ANNEX_TABLE_FIELD},
	)
	if not custom_field_name:
		return

	frappe.db.set_value("Custom Field", custom_field_name, "hidden", int(hidden))
	frappe.clear_cache(doctype="Sales Invoice")
