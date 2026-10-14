import { BusPlugin } from "@bus/services/bus_plugin";
import { _t } from "@web/core/l10n/translation";
import { NotificationPlugin } from "@web/core/notifications/notification_plugin";
import { user } from "@web/core/user";
import { patch } from "@web/core/utils/patch";
import { useLayoutEffect } from "@web/owl2/utils";
import { FormController } from "@web/views/form/form_controller";
import { onWillUnmount, usePlugin } from "@odoo/owl";

const NOTIFICATION_TYPE = "mercas_sale_order_lines_updated";

function busChannel(resId) {
    return `mercas_sale_order_lines-${resId}`;
}

patch(FormController.prototype, {
    setup() {
        super.setup();
        if (this.props.resModel !== "sale.order") {
            return;
        }

        const busService = usePlugin(BusPlugin);
        const notificationService = usePlugin(NotificationPlugin);

        useLayoutEffect(
            (resId) => {
                if (!resId) {
                    return;
                }
                const channel = busChannel(resId);
                busService.addChannel(channel);
                return () => busService.deleteChannel(channel);
            },
            () => [this.model.root.resId]
        );

        const onLinesUpdated = (payload) => {
            const resId = this.model.root.resId;
            if (!resId || payload.order_id !== resId) {
                return;
            }
            if (payload.user_id === user.userId) {
                return;
            }
            notificationService.add(
                _t(
                    "%(user)s ha modificado las líneas de este pedido. Haz clic aquí para recargar.",
                    { user: payload.user_name }
                ),
                {
                    title: _t("Pedido actualizado"),
                    type: "warning",
                    sticky: true,
                    buttons: [
                        {
                            name: _t("Recargar"),
                            primary: true,
                            onClick: () => this.model.load(),
                        },
                    ],
                }
            );
        };

        busService.subscribe(NOTIFICATION_TYPE, onLinesUpdated);
        onWillUnmount(() => busService.unsubscribe(NOTIFICATION_TYPE, onLinesUpdated));
    },
});
