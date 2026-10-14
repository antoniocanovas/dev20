import { _t } from "@web/core/l10n/translation";
import { formatDateTime } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { usePopover } from "@web/core/popover/popover_hook";

import { Component, t, useProps } from "@odoo/owl";

class ProductQtyDatetimeIconPopover extends Component {
    static template = "mercas_base.ProductQtyDatetimeIconPopover";
    props = useProps({ text: t.string(), close: t.function() });
}

export class ProductQtyDatetimeIcon extends Component {
    static template = "mercas_base.ProductQtyDatetimeIcon";
    static components = { Popover: ProductQtyDatetimeIconPopover };
    props = useProps(standardFieldProps);

    setup() {
        this.popover = usePopover(this.constructor.components.Popover, { position: "top" });
    }

    get text() {
        const value = this.props.record.data[this.props.name];
        return value
            ? _t("Cantidad actualizada el: %s", formatDateTime(value))
            : _t("Cantidad actualizada el:");
    }

    showPopover(ev) {
        this.popover.open(ev.currentTarget, { text: this.text });
    }
}

export const productQtyDatetimeIcon = {
    component: ProductQtyDatetimeIcon,
    supportedTypes: ["datetime"],
    listViewWidth: 32,
};

registry.category("fields").add("mercas_product_qty_datetime_icon", productQtyDatetimeIcon);
