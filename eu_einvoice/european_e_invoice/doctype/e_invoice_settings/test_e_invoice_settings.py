# Copyright (c) 2025, ALYF GmbH and Contributors
# See license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
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
			patch(f"{ANNEX_MODULE}._set_multi_annex_field_visibility") as set_visibility,
		):
			sync_sales_invoice_annex_field(True)

		create_custom_fields.assert_called_once_with(get_sales_invoice_annex_custom_fields())
		set_visibility.assert_called_once_with(enabled=True)

	def test_hides_field_when_toggled_off_again(self):
		with (
			patch(f"{ANNEX_MODULE}.sales_invoice_annex_table_installed", return_value=True),
			patch(f"{ANNEX_MODULE}._set_multi_annex_field_visibility") as set_visibility,
			patch(f"{ANNEX_MODULE}.create_custom_fields") as create_custom_fields,
		):
			sync_sales_invoice_annex_field(False)

		set_visibility.assert_called_once_with(enabled=False)
		create_custom_fields.assert_not_called()

	def test_unhides_field_when_toggled_on_again(self):
		with (
			patch(f"{ANNEX_MODULE}.sales_invoice_annex_table_installed", return_value=True),
			patch(f"{ANNEX_MODULE}._set_multi_annex_field_visibility") as set_visibility,
			patch(f"{ANNEX_MODULE}.create_custom_fields") as create_custom_fields,
		):
			sync_sales_invoice_annex_field(True)

		set_visibility.assert_called_once_with(enabled=True)
		create_custom_fields.assert_not_called()

	def test_clears_content_validation_when_multi_annex_disabled(self):
		settings = frappe.get_single("E Invoice Settings")
		settings.multi_annex_embed_enabled = 1
		settings.annex_validation_by_content_enabled = 1
		settings.save()

		settings.multi_annex_embed_enabled = 0
		settings.save()
		settings.reload()

		self.assertFalse(settings.annex_validation_by_content_enabled)
