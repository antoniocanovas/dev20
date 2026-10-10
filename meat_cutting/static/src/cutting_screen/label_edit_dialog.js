import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { formatFloat } from "@web/core/utils/numbers";

const LINE_MODEL = "meat.cutting.line";

/**
 * Edit the texts printed on the label of a cut. They are saved on the line
 * only: the crotal keeps its data. Lot, crotal and weight are not editable as
 * they carry the traceability of the cut (and the GS1 barcode).
 */
export class LabelEditDialog extends Component {
    static template = "meat_cutting.LabelEditDialog";
    static components = { Dialog };
    props = useProps({
        close: t.function(),
        lineId: t.number(),
        print: t.function(),
        onSaved: t.function().optional(),
    });

    setup() {
        this.orm = useService("orm");
        this.title = _t("Edit label");
        this.fields = [
            { key: "product_name", label: _t("Product") },
            { key: "birth_country", label: _t("Born in") },
            { key: "reared_country", label: _t("Reared in") },
            { key: "slaughter_date", label: _t("Slaughtered"), type: "date" },
            { key: "origin", label: _t("Origin") },
            { key: "supplier", label: _t("Supplier") },
            { key: "note", label: _t("Note"), placeholder: _t("e.g. Keep between 0 and 4 °C") },
        ];
        this.state = proxy({ data: null, values: {}, busy: false });
        onWillStart(async () => {
            const data = await this.orm.call(LINE_MODEL, "get_label_data", [[this.props.lineId]]);
            this.state.data = data;
            this.state.values = { ...data.values };
        });
    }

    get weight() {
        return formatFloat(this.state.data.weight, { digits: [false, 3] });
    }

    isChanged(key) {
        return (this.state.values[key] || "") !== (this.state.data.defaults[key] || "");
    }

    onInput(key, ev) {
        this.state.values[key] = ev.target.value;
    }

    restoreField(key) {
        this.state.values[key] = this.state.data.defaults[key] || "";
    }

    async run(callback) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await callback();
            await this.props.onSaved?.();
            this.props.close();
        } finally {
            this.state.busy = false;
        }
    }

    async save() {
        const changed = this.fields.some((field) => this.isChanged(field.key));
        if (changed) {
            await this.orm.call(LINE_MODEL, "action_save_label", [[this.props.lineId], this.state.values]);
        } else if (this.state.data.custom) {
            // Back to the defaults: follow the crotal again
            await this.orm.call(LINE_MODEL, "action_reset_label", [[this.props.lineId]]);
        }
    }

    onSave() {
        return this.run(() => this.save());
    }

    onSaveAndPrint() {
        return this.run(async () => {
            await this.save();
            await this.props.print(this.props.lineId);
        });
    }

    onRestoreAll() {
        for (const field of this.fields) {
            this.restoreField(field.key);
        }
    }
}
