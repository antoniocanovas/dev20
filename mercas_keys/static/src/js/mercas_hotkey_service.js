import { registry } from "@web/core/registry";
import { MODES, modeAction, addLineAndFocusProduct } from "./mercas_modes";

registry.category("services").add("mercas_hotkeys", {
    dependencies: ["action"],
    start(_env, { action: actionService }) {
        const handler = (ev) => {
            const mode = MODES.find((m) => m.fkey === ev.key);
            if (mode) {
                ev.preventDefault();
                actionService.doAction(modeAction(mode));
                return;
            }
            if (ev.key === "Insert") {
                ev.preventDefault();
                addLineAndFocusProduct();
            }
        };
        document.addEventListener("keydown", handler, { capture: true });
    },
});
