# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from eu_einvoice.annex.attachments import (
	EInvoiceAnnexAttachment,
	_attachments_from_legacy,
	get_attachments_from_annex_table,
	has_annex_attachments,
)
from eu_einvoice.annex.test_helpers import (
	append_annex_rows,
	create_test_file,
	delete_test_file,
	make_sales_invoice_doc,
	patch_multi_annex_enabled,
)


class TestGetAnnexAttachments(UnitTestCase):
	def test_has_annex_attachments_off_legacy_on_table_ignored(self):
		doc = make_sales_invoice_doc(
			einvoice_embedded_document="/files/legacy.png",
		)
		append_annex_rows(doc, [{"file": "F-TABLE-1", "display_name": "Table"}])

		with patch_multi_annex_enabled(False):
			self.assertTrue(has_annex_attachments(doc))

	def test_has_annex_attachments_on_table_only(self):
		doc = make_sales_invoice_doc(
			einvoice_embedded_document="/files/legacy.png",
		)

		with patch_multi_annex_enabled(True):
			self.assertFalse(has_annex_attachments(doc))

		append_annex_rows(doc, [{"file": "F-TABLE-1", "display_name": "Table"}])

		with patch_multi_annex_enabled(True):
			self.assertTrue(has_annex_attachments(doc))

		with patch_multi_annex_enabled(False):
			self.assertTrue(has_annex_attachments(doc))

	def test_table_path_ignores_legacy_field(self):
		doc = make_sales_invoice_doc(
			einvoice_embedded_document="/files/legacy.png",
		)
		append_annex_rows(
			doc,
			[
				{"file": "F-TABLE-1", "display_name": "First"},
				{"file": "F-TABLE-2", "display_name": "Second"},
			],
		)

		with patch(
			"eu_einvoice.annex.attachments.EInvoiceAnnexAttachment.from_annex_row",
			side_effect=lambda row: EInvoiceAnnexAttachment(
				file_id=row.file,
				basename=f"{row.file}.png",
				mime_type="image/png",
				content=b"x",
				issuer_assigned_id=row.file,
				row_idx=row.idx,
			),
		) as from_row:
			result = get_attachments_from_annex_table(doc)

		self.assertEqual(from_row.call_count, 2)
		self.assertEqual([item.file_id for item in result], ["F-TABLE-1", "F-TABLE-2"])

	def test_on_returns_table_rows_in_idx_order(self):
		doc = make_sales_invoice_doc()
		append_annex_rows(
			doc,
			[
				{"file": "F-ROW-2", "display_name": "Second", "idx": 2},
				{"file": "F-ROW-1", "display_name": "First", "idx": 1},
			],
		)

		with patch_multi_annex_enabled(True):
			with patch(
				"eu_einvoice.annex.attachments.EInvoiceAnnexAttachment.from_annex_row",
				side_effect=lambda row: EInvoiceAnnexAttachment(
					file_id=row.file,
					basename=f"{row.file}.png",
					mime_type="image/png",
					content=b"x",
					issuer_assigned_id=row.file,
					row_idx=row.idx,
				),
			):
				result = get_attachments_from_annex_table(doc)

		self.assertEqual([item.file_id for item in result], ["F-ROW-1", "F-ROW-2"])
		self.assertEqual([item.row_idx for item in result], [1, 2])

	def test_get_annex_without_annexes_returns_empty(self):
		doc = make_sales_invoice_doc()

		self.assertEqual(get_attachments_from_annex_table(doc), [])

	def test_missing_file_throws(self):
		doc = make_sales_invoice_doc()
		append_annex_rows(doc, [{"file": "F-DOES-NOT-EXIST", "display_name": "Broken"}])

		with self.assertRaises(frappe.DoesNotExistError):
			get_attachments_from_annex_table(doc)

	def test_legacy_missing_file_throws(self):
		with self.assertRaises(frappe.ValidationError):
			_attachments_from_legacy("/files/missing.png")

	def test_wrong_doctype_throws(self):
		doc = frappe.new_doc("Customer")

		with self.assertRaises(frappe.ValidationError):
			get_attachments_from_annex_table(doc)

	def test_from_file_remote_skips_content_and_mime(self):
		attachment = EInvoiceAnnexAttachment.from_file(
			frappe._dict(
				name="F-REMOTE",
				file_name="remote.pdf",
				file_url="https://example.com/remote.pdf",
				is_remote_file=1,
			),
			row_idx=1,
		)

		self.assertIsNone(attachment.content)
		self.assertIsNone(attachment.mime_type)
		self.assertEqual(attachment.basename, "remote.pdf")
		self.assertEqual(attachment.file_id, "F-REMOTE")
		self.assertEqual(attachment.row_idx, 1)

	def test_legacy_path_logs_deprecation_once(self):
		frappe.flags.annex_legacy_deprecation_logged = False

		with patch(
			"eu_einvoice.annex.attachments.find_file_by_url",
			return_value=frappe._dict(
				name="F-LEGACY",
				file_name="legacy.png",
				file_url="/files/legacy.png",
				is_remote_file=0,
				get_content=lambda: b"x",
			),
		):
			with patch("eu_einvoice.annex.attachments.frappe.logger") as get_logger:
				logger = get_logger.return_value
				_attachments_from_legacy("/files/legacy.png")
				_attachments_from_legacy("/files/legacy.png")

		logger.warning.assert_called_once()


class IntegrationTestGetAnnexAttachments(IntegrationTestCase):
	def test_local_file_attachment_fields(self):
		file_doc = create_test_file(file_name="annex-local.png", name="F-LOCAL-FIELDS")
		self.addCleanup(delete_test_file, file_doc.name)

		doc = make_sales_invoice_doc()
		append_annex_rows(doc, [{"file": file_doc.name, "display_name": "Local"}])

		with patch_multi_annex_enabled(True):
			result = get_attachments_from_annex_table(doc)

		self.assertEqual(len(result), 1)
		attachment = result[0]
		self.assertEqual(attachment.file_id, file_doc.name)
		self.assertEqual(attachment.basename, "annex-local.png")
		self.assertEqual(attachment.mime_type, "image/png")
		self.assertEqual(attachment.content, file_doc.get_content())
		self.assertEqual(attachment.issuer_assigned_id, file_doc.name)
		self.assertEqual(attachment.row_idx, 1)

	def test_on_two_files_from_database(self):
		first = create_test_file(file_name="annex-a.png", name="F-ANNEX-A")
		second = create_test_file(file_name="annex-b.png", name="F-ANNEX-B")
		self.addCleanup(delete_test_file, first.name)
		self.addCleanup(delete_test_file, second.name)

		doc = make_sales_invoice_doc()
		append_annex_rows(
			doc,
			[
				{"file": second.name, "display_name": "B", "idx": 2},
				{"file": first.name, "display_name": "A", "idx": 1},
			],
		)

		with patch_multi_annex_enabled(True):
			result = get_attachments_from_annex_table(doc)

		self.assertEqual([item.file_id for item in result], [first.name, second.name])


class IntegrationTestSettingsEnableOnce(IntegrationTestCase):
	def test_settings_cannot_disable_multi_annex(self):
		settings = frappe.get_single("E Invoice Settings")
		previous = bool(settings.multi_annex_embed_enabled)
		self.addCleanup(
			lambda: frappe.db.set_single_value(
				"E Invoice Settings",
				"multi_annex_embed_enabled",
				int(previous),
				update_modified=False,
			)
		)

		settings.multi_annex_embed_enabled = 1
		settings.save()

		settings.multi_annex_embed_enabled = 0
		with self.assertRaises(frappe.ValidationError):
			settings.save()
