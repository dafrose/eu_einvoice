# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""XRechnung annex file validation (MIME allowlist, content sniffing)."""

from eu_einvoice.annex.attachments import (
	EInvoiceAnnexAttachment,
	get_attachments_from_annex_table,
	has_annex_attachments,
	is_multi_annex_embed_enabled,
)

__all__ = [
	"EInvoiceAnnexAttachment",
	"get_attachments_from_annex_table",
	"has_annex_attachments",
	"is_multi_annex_embed_enabled",
]
