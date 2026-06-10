# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

from __future__ import annotations

import base64
from contextlib import contextmanager
from unittest.mock import patch

import frappe

TEST_FILE_CONTENT = base64.b64decode("iVBORw0KGgo=")

def make_sales_invoice_doc(**kwargs) -> frappe.model.document.Document:
	doc = frappe.new_doc("Sales Invoice")
	doc.update(kwargs)
	return doc


def append_annex_rows(doc, rows: list[dict]) -> None:
	for row in rows:
		doc.append("einvoice_annexes", row)


def delete_test_file(name: str) -> None:
	if frappe.db.exists("File", name):
		frappe.delete_doc("File", name, force=True)


def create_test_file(*, file_name: str, name: str | None = None) -> frappe.model.document.Document:
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


@contextmanager
def patch_multi_annex_enabled(enabled: bool):
	original = frappe.db.get_single_value

	def mock_get_single_value(doctype, fieldname, *args, **kwargs):
		if doctype == "E Invoice Settings" and fieldname == "multi_annex_embed_enabled":
			return int(enabled)
		return original(doctype, fieldname, *args, **kwargs)

	with patch.object(frappe.db, "get_single_value", side_effect=mock_get_single_value):
		yield
