frappe.ui.form.on("Sales Invoice", {
	setup(frm) {
		if (frm.fields_dict.einvoice_annexes) {
			frm.set_query("file", "einvoice_annexes", function () {
				if (frm.is_new()) {
					return { filters: { name: ["in", []] } };
				}
				return {
					filters: {
						attached_to_doctype: frm.doctype,
						attached_to_name: frm.doc.name,
					},
				};
			});
		}
	},
	refresh: function (frm) {
		frm.trigger("add_einvoice_button");

		if (!frm.is_dirty() && !frm.doc.einvoice_is_correct && frm.doc.einvoice_profile) {
			frm.dashboard.set_headline_alert(__("Please note the validation errors of the e-invoice."));
		}
	},
	add_einvoice_button: function (frm) {
		if (frm.is_new() || !frm.doc.einvoice_profile) {
			return;
		}

		frm.page.add_menu_item(__("Download eInvoice"), () => {
			window.open(
				`/api/method/eu_einvoice.european_e_invoice.custom.sales_invoice.download_xrechnung?invoice_id=${encodeURIComponent(
					frm.doc.name
				)}`,
				"_blank"
			);
		});
	},
});

frappe.ui.form.on("E Invoice Annex Row", {
	async file(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.file) {
			return;
		}
		const r = await frappe.call({
			method: "eu_einvoice.annex.validation.is_annex_extension_allowed_for_file_id",
			args: { file_id: row.file },
		});
		if (!r.message) {
			await warn_annex_extension_not_allowed(frm);
		}
	},
});

async function warn_annex_extension_not_allowed(frm) {
	if (!frm._einvoice_annex_allowed_extensions_text) {
		const r = await frappe.call({
			method: "eu_einvoice.annex.validation.get_annex_allowed_extensions_text",
		});
		frm._einvoice_annex_allowed_extensions_text = r.message || "";
	}

	frappe.msgprint({
		title: __("E-Invoice annex not allowed"),
		message: __("Allowed file extensions: {0}", [frm._einvoice_annex_allowed_extensions_text]),
		indicator: "orange",
	});
}
