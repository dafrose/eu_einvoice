# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import frappe
import yaml
from frappe.tests import IntegrationTestCase, UnitTestCase

from eu_einvoice.annex.validation import (
	EXTENSION_CONTENT_MIMES,
	detect_annex_mime_from_content,
	get_annex_allowed_extensions,
	is_annex_extension_allowed_for_file_id,
	validate_annex_file,
)

VALIDATION_MODULE = "eu_einvoice.annex.validation"
SCENARIOS_YAML = Path(__file__).with_name("annex_mime_allowlist_scenarios.yaml")


@dataclass(frozen=True)
class AnnexScenario:
	extension: str
	filename: str
	accept_extension: bool
	mimetype: str | None = None
	content_bytes: bytes | None = None
	accept_validation: bool | None = None
	file_id: str = "FILE-TEST"
	expect_error_contains: str | None = None
	test_integration: bool = False


def load_annex_scenarios() -> list[AnnexScenario]:
	raw = yaml.safe_load(SCENARIOS_YAML.read_text())

	scenarios: list[AnnexScenario] = []
	for row in raw:

		extension = row.get("extension")
		filename = row.get("filename")

		content_b64 = row.get("content_bytes_b64")
		content_bytes = base64.b64decode(content_b64) if content_b64 else None
		mimetype = row.get("mimetype")
		accept_validation = row.get("accept_validation")
		expect_error_contains = row.get("expect_error_contains")

		scenarios.append(
			AnnexScenario(
				extension=extension,
				filename=filename,
				accept_extension=bool(row["accept_extension"]),
				mimetype=mimetype,
				content_bytes=content_bytes,
				accept_validation=accept_validation,
				file_id=row.get("file_id", "FILE-TEST"),
				expect_error_contains=expect_error_contains,
				test_integration=bool(row.get("test_integration", False)),
			)
		)

	return scenarios


def scenarios_with_content(scenarios: list[AnnexScenario]) -> list[AnnexScenario]:
	return [scenario for scenario in scenarios if scenario.content_bytes is not None]


def integration_scenarios(scenarios: list[AnnexScenario]) -> list[AnnexScenario]:
	return [scenario for scenario in scenarios if scenario.test_integration]


def _delete_test_file(name: str) -> None:
	if frappe.db.exists("File", name):
		frappe.delete_doc("File", name, force=True)


class TestAnnexMimeAllowlist(UnitTestCase):
	def test_allowlist_matches_scenarios(self):
		scenarios = load_annex_scenarios()
		allowed_extensions = get_annex_allowed_extensions()
		accepting_extensions: set[str] = set()
		accepting_mimes: set[str] = set()

		for scenario in scenarios:
			if scenario.accept_extension:
				accepting_extensions.add(scenario.extension)
				accepting_mimes.add(EXTENSION_CONTENT_MIMES[scenario.extension])
				self.assertIn(scenario.extension, allowed_extensions)
				if scenario.accept_validation:
					self.assertEqual(
						scenario.mimetype,
						EXTENSION_CONTENT_MIMES[scenario.extension],
					)

		for extension, mimetype in EXTENSION_CONTENT_MIMES.items():
			self.assertIn(
				mimetype,
				accepting_mimes,
				f"No accepting scenario for MIME type {mimetype} (extension {extension})",
			)

	def test_extension_only(self):
		for scenario in load_annex_scenarios():
			with self.subTest(filename=scenario.filename):
				with (
					patch(
						f"{VALIDATION_MODULE}.frappe.db.get_value",
						return_value=scenario.filename,
					) as get_value,
					patch(f"{VALIDATION_MODULE}.frappe.get_doc") as get_doc,
				):
					if scenario.accept_extension:
						validate_annex_file(
							scenario.file_id,
							validate_by_content=False,
						)
					else:
						with self.assertRaises(frappe.ValidationError):
							validate_annex_file(
								scenario.file_id,
								validate_by_content=False,
							)
					get_value.assert_called()
					get_doc.assert_not_called()

	def test_content_sniff(self):
		for scenario in scenarios_with_content(load_annex_scenarios()):
			with self.subTest(filename=scenario.filename):
				self.assertEqual(
					detect_annex_mime_from_content(
						scenario.content_bytes,
						file_name=scenario.filename,
					),
					scenario.mimetype,
				)

	def test_validation(self):
		for scenario in scenarios_with_content(load_annex_scenarios()):
			with self.subTest(filename=scenario.filename):
				with (
					patch(
						f"{VALIDATION_MODULE}.frappe.db.get_value",
						return_value=scenario.filename,
					),
					patch(f"{VALIDATION_MODULE}.frappe.get_doc") as get_doc,
				):
					get_doc.return_value.get_content.return_value = scenario.content_bytes
					if scenario.accept_validation:
						validate_annex_file(
							scenario.file_id,
							validate_by_content=True,
						)
					else:
						with self.assertRaises(frappe.ValidationError) as ctx:
							validate_annex_file(
								scenario.file_id,
								validate_by_content=True,
							)
						if scenario.expect_error_contains:
							self.assertIn(
								scenario.expect_error_contains,
								str(ctx.exception),
							)

	def test_skips_content_when_setting_disabled(self):
		with (
			patch(f"{VALIDATION_MODULE}.frappe.db.get_value", return_value="delivery.pdf"),
			patch(f"{VALIDATION_MODULE}.annex_validation_by_content_enabled", return_value=False),
			patch(f"{VALIDATION_MODULE}.frappe.get_doc") as get_doc,
		):
			validate_annex_file("FILE-00006")
			get_doc.assert_not_called()


class IntegrationTestAnnexExtensionApi(IntegrationTestCase):
	def test_extension_api_from_database(self):
		for scenario in integration_scenarios(load_annex_scenarios()):
			with self.subTest(filename=scenario.filename):
				file_doc = frappe.get_doc(
					{
						"doctype": "File",
						"file_name": scenario.filename,
						"content": scenario.content_bytes or b"test",
					}
				).insert()
				self.addCleanup(_delete_test_file, file_doc.name)

				self.assertEqual(
					is_annex_extension_allowed_for_file_id(file_doc.name),
					scenario.accept_extension,
				)
