# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

from __future__ import annotations

import base64
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from eu_einvoice.annex.sales_invoice import (
	deduplicate_annex_rows,
	migrate_embedded_document_to_annexes,
)
from eu_einvoice.european_e_invoice.custom.sales_invoice import validate_doc

TEST_FILE_CONTENT = base64.b64decode("iVBORw0KGgo=")


def _make_sales_invoice_doc(**kwargs) -> frappe.model.document.Document:
	doc = frappe.new_doc("Sales Invoice")
	doc.update(kwargs)
	return doc


def _append_annex_rows(doc, rows: list[dict]) -> None:
	for row in rows:
		doc.append("einvoice_annexes", row)


def _delete_test_file(name: str) -> None:
	if frappe.db.exists("File", name):
		frappe.delete_doc("File", name, force=True)


def _create_test_file(*, file_name: str, name: str | None = None) -> frappe.model.document.Document:
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"content": TEST_FILE_CONTENT,
		}
	).insert(ignore_permissions=True)

	if name and file_doc.name != name:
		frappe.rename_doc("File", file_doc.name, name, force=True)
		file_doc = frappe.get_doc("File", name)

	return file_doc


def _run_sales_invoice_annex_processing(doc, *, multi_annex_enabled: bool) -> None:
	"""Mirror the annex branch in ``validate_doc`` (caller-owned prerequisites)."""
	if multi_annex_enabled:
		if doc.einvoice_embedded_document:
			migrate_embedded_document_to_annexes(doc)
		if doc.einvoice_annexes:
			deduplicate_annex_rows(doc)


class TestDeduplicateAnnexRows(UnitTestCase):
	def test_deduplicate_last_wins(self):
		cases = [
			(
				"two_rows",
				[
					{"file": "F-DEDUP-1", "display_name": "First"},
					{"file": "F-DEDUP-1", "display_name": "Last"},
				],
				1,
				["F-DEDUP-1"],
				["Last"],
			),
			(
				"three_rows",
				[
					{"file": "F-DEDUP-A", "display_name": "A"},
					{"file": "F-DEDUP-A", "display_name": "B"},
					{"file": "F-DEDUP-B", "display_name": "C"},
				],
				2,
				["F-DEDUP-A", "F-DEDUP-B"],
				["B", "C"],
			),
		]
		for name, annex_rows, annex_count, files, display_names in cases:
			with self.subTest(name=name):
				doc = _make_sales_invoice_doc()
				_append_annex_rows(doc, annex_rows)
				deduplicate_annex_rows(doc)

				self.assertEqual(len(doc.einvoice_annexes), annex_count)
				self.assertEqual([row.file for row in doc.einvoice_annexes], files)
				self.assertEqual(
					[row.display_name or "" for row in doc.einvoice_annexes],
					display_names,
				)


class IntegrationTestAnnexSalesInvoiceMigration(IntegrationTestCase):
	def tearDown(self):
		super().tearDown()
		frappe.clear_messages()

	def test_migrate_legacy_only(self):
		file_doc = _create_test_file(file_name="annex-migrate.png")
		self.addCleanup(_delete_test_file, file_doc.name)
		frappe.clear_messages()

		doc = _make_sales_invoice_doc(einvoice_embedded_document=file_doc.file_url)
		_run_sales_invoice_annex_processing(doc, multi_annex_enabled=True)

		self.assertFalse(doc.einvoice_embedded_document)
		self.assertEqual(len(doc.einvoice_annexes), 1)
		self.assertEqual(doc.einvoice_annexes[0].file, file_doc.name)
		messages = frappe.get_message_log()
		self.assertTrue(messages)
		self.assertEqual(messages[-1].indicator, "orange")

	def test_migrate_legacy_ignores_off(self):
		file_doc = _create_test_file(file_name="annex-migrate-off.png")
		self.addCleanup(_delete_test_file, file_doc.name)
		frappe.clear_messages()

		doc = _make_sales_invoice_doc(einvoice_embedded_document=file_doc.file_url)
		_run_sales_invoice_annex_processing(doc, multi_annex_enabled=False)

		self.assertEqual(doc.einvoice_embedded_document, file_doc.file_url)
		self.assertEqual(len(doc.einvoice_annexes), 0)
		self.assertFalse(frappe.get_message_log())

	def test_migrate_then_dedup(self):
		file_doc = _create_test_file(file_name="annex-same.png", name="F-MIGRATE-SAME")
		self.addCleanup(_delete_test_file, file_doc.name)
		frappe.clear_messages()

		doc = _make_sales_invoice_doc(einvoice_embedded_document=file_doc.file_url)
		_append_annex_rows(
			doc,
			[{"file": "F-MIGRATE-SAME", "display_name": "Existing"}],
		)
		_run_sales_invoice_annex_processing(doc, multi_annex_enabled=True)

		self.assertFalse(doc.einvoice_embedded_document)
		self.assertEqual(len(doc.einvoice_annexes), 1)
		self.assertEqual(doc.einvoice_annexes[0].file, "F-MIGRATE-SAME")
		self.assertEqual(doc.einvoice_annexes[0].display_name or "", "")
		messages = frappe.get_message_log()
		self.assertEqual(len(messages), 2)
		self.assertEqual(messages[0].indicator, "orange")
		self.assertEqual(messages[-1].indicator, "orange")
		self.assertIn("removed", messages[-1].message.lower())

	def test_migrate_legacy_missing_file(self):
		doc = _make_sales_invoice_doc(einvoice_embedded_document="/files/does-not-exist.png")
		_append_annex_rows(
			doc,
			[{"file": "F-ANNEX-ONLY", "display_name": "Annex only"}],
		)
		_run_sales_invoice_annex_processing(doc, multi_annex_enabled=True)

		self.assertFalse(doc.einvoice_embedded_document)
		self.assertEqual(len(doc.einvoice_annexes), 1)
		self.assertEqual(doc.einvoice_annexes[0].file, "F-ANNEX-ONLY")
		self.assertEqual(doc.einvoice_annexes[0].display_name, "Annex only")
		self.assertFalse(frappe.get_message_log())

	def test_validate_doc_runs_annex_processing(self):
		file_doc = _create_test_file(file_name="annex-migrate.png")
		self.addCleanup(_delete_test_file, file_doc.name)

		settings = frappe.get_single("E Invoice Settings")
		previous = bool(settings.multi_annex_embed_enabled)
		settings.multi_annex_embed_enabled = 1
		settings.save()
		self.addCleanup(
			lambda: frappe.db.set_single_value(
				"E Invoice Settings",
				"multi_annex_embed_enabled",
				int(previous),
				update_modified=False,
			)
		)

		with patch(
			"eu_einvoice.european_e_invoice.custom.sales_invoice.validate_annex_file"
		) as validate_file:
			doc = _make_sales_invoice_doc(einvoice_embedded_document=file_doc.file_url)
			validate_doc(doc, "validate")

		self.assertEqual(len(doc.einvoice_annexes), 1)
		self.assertFalse(doc.einvoice_embedded_document)
		validate_file.assert_called_once_with(file_doc.name, row_index=1)
