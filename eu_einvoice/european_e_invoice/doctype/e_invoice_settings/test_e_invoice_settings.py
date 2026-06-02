# Copyright (c) 2025, ALYF GmbH and Contributors
# See license.txt

from __future__ import annotations

from unittest.mock import patch

from frappe.tests import IntegrationTestCase

from eu_einvoice.european_e_invoice.custom.sales_invoice_annex import (
	get_sales_invoice_annex_custom_fields,
	sync_sales_invoice_annex_field,
)

ANNEX_MODULE = "eu_einvoice.european_e_invoice.custom.sales_invoice_annex"


class IntegrationTestEInvoiceSettings(IntegrationTestCase):
	def test_creates_field_when_first_toggled_on(self):
		with (
			patch(f"{ANNEX_MODULE}.sales_invoice_annex_table_installed", return_value=False),
			patch(f"{ANNEX_MODULE}.frappe.db.exists", return_value=True),
			patch(f"{ANNEX_MODULE}.create_custom_fields") as create_custom_fields,
			patch(f"{ANNEX_MODULE}._set_sales_invoice_annex_field_hidden") as set_hidden,
		):
			sync_sales_invoice_annex_field(True)

		create_custom_fields.assert_called_once_with(get_sales_invoice_annex_custom_fields())
		set_hidden.assert_not_called()

	def test_hides_field_when_toggled_off_again(self):
		with (
			patch(f"{ANNEX_MODULE}.sales_invoice_annex_table_installed", return_value=True),
			patch(f"{ANNEX_MODULE}._set_sales_invoice_annex_field_hidden") as set_hidden,
			patch(f"{ANNEX_MODULE}.create_custom_fields") as create_custom_fields,
		):
			sync_sales_invoice_annex_field(False)

		set_hidden.assert_called_once_with(hidden=True)
		create_custom_fields.assert_not_called()

	def test_unhides_field_when_toggled_on_again(self):
		with (
			patch(f"{ANNEX_MODULE}.sales_invoice_annex_table_installed", return_value=True),
			patch(f"{ANNEX_MODULE}._set_sales_invoice_annex_field_hidden") as set_hidden,
			patch(f"{ANNEX_MODULE}.refresh_sales_invoice_annex_field_description") as refresh_description,
			patch(f"{ANNEX_MODULE}.create_custom_fields") as create_custom_fields,
		):
			sync_sales_invoice_annex_field(True)

		set_hidden.assert_called_once_with(hidden=False)
		refresh_description.assert_called_once()
		create_custom_fields.assert_not_called()
