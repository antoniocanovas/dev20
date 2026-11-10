import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { TouchScreen } from "@scrap_touch/touch_screen/touch_screen";

const MODEL = "scrap.touch";

patch(TouchScreen.prototype, {
    /** Repair the vehicle to repair and sell: its repair not done yet, or a new one, opened in
     * a dialog to add its parts and services. */
    async onRepairVehicle() {
        const vehicle = this.state.vehicle;
        const repairId = await this.run("repair_vehicle", [vehicle.id]);
        if (!repairId || this.state.vehicle !== vehicle) {
            return;
        }
        await this.refreshVehicle();
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Repair of %s", vehicle.name),
            res_model: "repair.order",
            res_id: repairId,
            views: [[false, "form"]],
            target: "new",
        }, { onClose: () => this.refreshVehicle() });
    },
});
