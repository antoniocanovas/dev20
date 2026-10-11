import { Component, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { formatFloat } from "@web/core/utils/numbers";

/** Data of a package in stock kept out of its tile on the factory screen. */
export class PackageInfoDialog extends Component {
    static template = "meat_cutting.PackageInfoDialog";
    static components = { Dialog };
    props = useProps({
        close: t.function(),
        pack: t.object(),
    });

    get title() {
        return this.props.pack.package_name || _t("Lot %s", this.props.pack.lot_name);
    }

    get rows() {
        const pack = this.props.pack;
        return [
            { label: _t("Product"), value: pack.product_name },
            { label: _t("Internal Reference"), value: pack.default_code },
            { label: _t("Package"), value: pack.package_name },
            { label: _t("Lot"), value: pack.lot_name },
            { label: _t("Crotal"), value: pack.crotal_name },
            { label: _t("Presentation"), value: pack.presentation },
            { label: _t("Quantity"), value: `${formatFloat(pack.qty, { digits: [false, 3] })} ${pack.uom_name}` },
            { label: _t("Expiration Date"), value: pack.expiration_date.slice(0, 10) },
            { label: _t("Location"), value: pack.location_name },
        ].filter((row) => row.value);
    }
}
