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
		frm.trigger("setup_einvoice_annex_grid_attach_button");

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
	setup_einvoice_annex_grid_attach_button(frm) {
		const table_field = frm.fields_dict.einvoice_annexes;
		if (
			!table_field?.grid ||
			!frm.doc.einvoice_profile ||
			frm.doc.docstatus !== 0 ||
			table_field.df.hidden
		) {
			return;
		}

		table_field.grid.add_custom_button(__("Attach file"), () => {
			open_einvoice_annex_file_uploader(frm);
		});
	},
});

frappe.ui.form.on("E Invoice Annex Row", {
	async file(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.file) {
			return;
		}
		await warn_if_annex_extension_not_allowed(frm, row.file);
	},
});

function open_einvoice_annex_file_uploader(frm) {
	if (frm.is_new()) {
		frappe.msgprint({
			title: __("Save required"),
			message: __("Please save the Sales Invoice before attaching annex files."),
			indicator: "orange",
		});
		return;
	}

	new frappe.ui.FileUploader({
		doctype: frm.doctype,
		docname: frm.docname,
		fieldname: "einvoice_annexes",
		allow_multiple: false,
		make_attachments_public: frm.meta.make_attachments_public ? 1 : 0,
		on_success: (attachment) => {
			add_einvoice_annex_row_from_upload(frm, attachment.file_doc || attachment);
		},
	});
}

async function add_einvoice_annex_row_from_upload(frm, file_doc) {
	const row = frm.add_child("einvoice_annexes");
	row.file = file_doc.name;
	frm.refresh_field("einvoice_annexes");
	await warn_if_annex_extension_not_allowed(frm, file_doc.name);
}

async function warn_if_annex_extension_not_allowed(frm, file_id) {
	const r = await frappe.call({
		method: "eu_einvoice.annex.validation.is_annex_extension_allowed_for_file_id",
		args: { file_id },
	});
	if (!r.message) {
		await warn_annex_extension_not_allowed(frm);
	}
}

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
