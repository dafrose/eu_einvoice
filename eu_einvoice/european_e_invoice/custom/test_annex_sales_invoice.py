# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from drafthorse.models.document import Document
from frappe.tests import IntegrationTestCase, UnitTestCase

from eu_einvoice.annex.sales_invoice import (
	deduplicate_annex_rows,
	migrate_embedded_document_to_annexes,
)
from eu_einvoice.annex.test_helpers import (
	append_annex_rows,
	create_test_file,
	delete_test_file,
	make_sales_invoice_doc,
	patch_multi_annex_enabled,
)
from eu_einvoice.european_e_invoice.custom.sales_invoice import EInvoiceGenerator, validate_doc
from eu_einvoice.utils import EInvoiceProfile


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
				doc = make_sales_invoice_doc()
				append_annex_rows(doc, annex_rows)
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
		file_doc = create_test_file(file_name="annex-migrate.png")
		self.addCleanup(delete_test_file, file_doc.name)
		frappe.clear_messages()

		doc = make_sales_invoice_doc(einvoice_embedded_document=file_doc.file_url)
		migrate_embedded_document_to_annexes(doc)

		self.assertFalse(doc.einvoice_embedded_document)
		self.assertEqual(len(doc.einvoice_annexes), 1)
		self.assertEqual(doc.einvoice_annexes[0].file, file_doc.name)
		messages = frappe.get_message_log()
		self.assertTrue(messages)
		self.assertEqual(messages[-1].indicator, "orange")

	def test_migrate_legacy_missing_file(self):
		doc = make_sales_invoice_doc(einvoice_embedded_document="/files/does-not-exist.png")

		with self.assertRaises(frappe.ValidationError):
			migrate_embedded_document_to_annexes(doc)

	def test_migrate_then_dedup(self):
		file_doc = create_test_file(file_name="annex-same.png", name="F-MIGRATE-SAME")
		self.addCleanup(delete_test_file, file_doc.name)
		frappe.clear_messages()

		doc = make_sales_invoice_doc(einvoice_embedded_document=file_doc.file_url)
		append_annex_rows(
			doc,
			[{"file": "F-MIGRATE-SAME", "display_name": "Existing"}],
		)
		migrate_embedded_document_to_annexes(doc)
		deduplicate_annex_rows(doc)

		self.assertFalse(doc.einvoice_embedded_document)
		self.assertEqual(len(doc.einvoice_annexes), 1)
		self.assertEqual(doc.einvoice_annexes[0].file, "F-MIGRATE-SAME")
		self.assertEqual(doc.einvoice_annexes[0].display_name or "", "")
		messages = frappe.get_message_log()
		self.assertEqual(len(messages), 2)
		self.assertEqual(messages[0].indicator, "orange")
		self.assertEqual(messages[-1].indicator, "orange")
		self.assertIn("removed", messages[-1].message.lower())

	def test_validate_doc_blocks_new_legacy_writes(self):
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

		doc = make_sales_invoice_doc()
		doc.einvoice_embedded_document = "/files/changed-legacy.png"

		with patch.object(doc, "has_value_changed", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				validate_doc(doc, "validate")

	def test_validate_doc_runs_annex_processing(self):
		file_doc = create_test_file(file_name="annex-validate.png", name="F-ANNEX-VALIDATE")
		self.addCleanup(delete_test_file, file_doc.name)

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
			doc = make_sales_invoice_doc()
			append_annex_rows(doc, [{"file": file_doc.name, "display_name": "Annex"}])
			validate_doc(doc, "validate")

		validate_file.assert_called_once_with(file_doc.name, row_index=1)


def _make_einvoice_generator(invoice):
	generator = EInvoiceGenerator(
		profile=EInvoiceProfile.EN16931,
		invoice=invoice,
		company=frappe._dict(name="Test Co"),
		customer=frappe._dict(name="Test Customer", supplier_numbers=[]),
	)
	generator.doc = Document()
	return generator


class TestEmbedAttachmentWiring(UnitTestCase):
	def test_legacy_path_when_feature_off(self):
		doc = make_sales_invoice_doc(einvoice_embedded_document="/files/legacy.png")
		append_annex_rows(doc, [{"file": "F-TABLE-1", "display_name": "Ignored"}])
		generator = _make_einvoice_generator(doc)

		with patch_multi_annex_enabled(False):
			with patch(
				"eu_einvoice.european_e_invoice.custom.sales_invoice.find_file_by_url",
				return_value=frappe._dict(
					name="F-LEGACY",
					file_url="/files/legacy.png",
					is_remote_file=0,
					get_content=lambda: b"legacy-bytes",
				),
			):
				with patch(
					"eu_einvoice.european_e_invoice.custom.sales_invoice.get_attachments_from_annex_table"
				) as get_annexes:
					with patch(
						"eu_einvoice.european_e_invoice.custom.sales_invoice._log_legacy_deprecation_once"
					) as log_deprecation:
						generator._embed_attachment()

		get_annexes.assert_not_called()
		log_deprecation.assert_called_once()
		self.assertEqual(len(generator.doc.trade.agreement.additional_references.children), 1)
		ref = generator.doc.trade.agreement.additional_references.children[0]
		self.assertIn("F-LEGACY", str(ref.issuer_assigned_id))

	def test_table_path_when_feature_on(self):
		doc = make_sales_invoice_doc(einvoice_embedded_document="/files/legacy.png")
		append_annex_rows(doc, [{"file": "F-TABLE-1", "display_name": "Used"}])
		generator = _make_einvoice_generator(doc)

		from eu_einvoice.annex.attachments import EInvoiceAnnexAttachment

		with patch_multi_annex_enabled(True):
			with patch(
				"eu_einvoice.european_e_invoice.custom.sales_invoice.get_attachments_from_annex_table",
				return_value=[
					EInvoiceAnnexAttachment(
						file_id="F-TABLE-1",
						basename="used.png",
						mime_type="image/png",
						content=b"table-bytes",
						issuer_assigned_id="F-TABLE-1",
						row_idx=1,
					)
				],
			) as get_annexes:
				with patch(
					"eu_einvoice.european_e_invoice.custom.sales_invoice.find_file_by_url"
				) as find_file:
					generator._embed_attachment()

		get_annexes.assert_called_once_with(doc)
		find_file.assert_not_called()
		self.assertEqual(len(generator.doc.trade.agreement.additional_references.children), 1)
		ref = generator.doc.trade.agreement.additional_references.children[0]
		self.assertIn("F-TABLE-1", str(ref.issuer_assigned_id))

	def test_enabled_ignores_legacy_without_table_rows(self):
		doc = make_sales_invoice_doc(einvoice_embedded_document="/files/legacy.png")
		generator = _make_einvoice_generator(doc)

		with patch_multi_annex_enabled(True):
			with patch(
				"eu_einvoice.european_e_invoice.custom.sales_invoice.find_file_by_url"
			) as find_file:
				generator._embed_attachment()

		find_file.assert_not_called()
		self.assertEqual(len(generator.doc.trade.agreement.additional_references.children), 0)


class IntegrationTestEmbedAttachmentLegacyPath(IntegrationTestCase):
	def test_legacy_file_embedded_when_feature_off(self):
		file_doc = create_test_file(file_name="legacy-embed.png", name="F-LEGACY-EMBED")
		self.addCleanup(delete_test_file, file_doc.name)
		frappe.flags.annex_legacy_deprecation_logged = False

		doc = make_sales_invoice_doc(einvoice_embedded_document=file_doc.file_url)
		generator = _make_einvoice_generator(doc)

		with patch_multi_annex_enabled(False):
			generator._embed_attachment()

		refs = generator.doc.trade.agreement.additional_references.children
		self.assertEqual(len(refs), 1)
		ref = refs[0]
		self.assertIn(file_doc.name, str(ref.issuer_assigned_id))
		self.assertTrue(ref.attached_object)
