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
SALES_INVOICE_EMBEDDED_DOCUMENT_FIELD = "einvoice_embedded_document"
E_INVOICE_ANNEX_ROW_DOCTYPE = "E Invoice Annex Row"


def sales_invoice_annex_table_installed() -> bool:
	return bool(
		frappe.db.exists(
			"Custom Field",
			{"dt": "Sales Invoice", "fieldname": SALES_INVOICE_ANNEX_TABLE_FIELD},
		)
	)


def get_sales_invoice_annex_table_field_description() -> str:
	"""Get the description for the sales invoice annex table field."""
	return _(
		"Add attachment files to embed into sales invoice PDF and/or XML. "
		"Allowed extensions: {extensions}. "
		"<br><b>Print format example:</b><br>"
		"<pre>{{% if doc.einvoice_annexes %}}"
		"{{% for row in doc.einvoice_annexes %}}"
		"{{% if row.display_name %}}"
		"&lt;p&gt;{{{{ row.display_name }}}}&lt;/p&gt;"
		"{{% endif %}}"
		"{{% endfor %}}"
		"{{% endif %}}</pre>"
	).format(extensions=get_annex_allowed_extensions_text())


def get_sales_invoice_annex_custom_fields() -> dict:
	return {
		"Sales Invoice": [
			{
				"fieldname": SALES_INVOICE_ANNEX_TABLE_FIELD,
				"label": _("Embedded Documents"),
				"fieldtype": "Table",
				"options": E_INVOICE_ANNEX_ROW_DOCTYPE,
				"insert_after": SALES_INVOICE_EMBEDDED_DOCUMENT_FIELD,
				"hidden": 0,
				"description": get_sales_invoice_annex_table_field_description(),
			},
		],
	}


def sync_sales_invoice_annex_field(enabled: bool) -> None:
	"""Create or toggle multi-annex fields on **Sales Invoice**."""
	if enabled:
		if sales_invoice_annex_table_installed():
			_set_multi_annex_field_visibility(enabled=True)
		else:
			_create_sales_invoice_annex_field()
	else:
		_set_multi_annex_field_visibility(enabled=False)
	frappe.clear_cache(doctype="Sales Invoice")



def _create_sales_invoice_annex_field() -> None:
	"""Create the sales invoice annex table field."""
	if not frappe.db.exists("DocType", E_INVOICE_ANNEX_ROW_DOCTYPE):
		frappe.throw(
			_(
				"DocType {0} is not installed. Run bench migrate for app european e-Invoice, then try again."
			).format(E_INVOICE_ANNEX_ROW_DOCTYPE)
		)

	create_custom_fields(get_sales_invoice_annex_custom_fields())
	_set_multi_annex_field_visibility(enabled=True)


def _set_multi_annex_field_visibility(*, enabled: bool) -> None:
	"""Set the visibility of the sales invoice annex table and embedded document fields. 
	Only one of the two fields is visible at a time.
	"""
	_set_custom_field_hidden(SALES_INVOICE_ANNEX_TABLE_FIELD, hidden=not enabled)
	_set_custom_field_hidden(SALES_INVOICE_EMBEDDED_DOCUMENT_FIELD, hidden=enabled)
	_set_custom_field_read_only(SALES_INVOICE_EMBEDDED_DOCUMENT_FIELD, read_only=enabled)


def _set_custom_field_hidden(fieldname: str, *, hidden: bool) -> None:
	custom_field_name = frappe.db.get_value(
		"Custom Field",
		{"dt": "Sales Invoice", "fieldname": fieldname},
	)
	if not custom_field_name:
		return

	frappe.db.set_value("Custom Field", custom_field_name, "hidden", int(hidden))


def _set_custom_field_read_only(fieldname: str, *, read_only: bool) -> None:
	custom_field_name = frappe.db.get_value(
		"Custom Field",
		{"dt": "Sales Invoice", "fieldname": fieldname},
	)
	if not custom_field_name:
		return

	frappe.db.set_value("Custom Field", custom_field_name, "read_only", int(read_only))
