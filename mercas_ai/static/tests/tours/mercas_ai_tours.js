import { registry } from "@web/core/registry";

// Loads the screens with their own widgets: the chat of mercas_ai and the dashboard of
// odoo_mcp_manager, which it depends on
registry.category("web_tour.tours").add("mercas_ai_chat_tour", {
    steps: () => [
        {
            content: "The chat with its history and message widgets",
            trigger: ".o_field_mercas_chat_history",
        },
        {
            trigger: ".o_field_mercas_chat_message textarea",
            run: "edit Hello",
        },
    ],
});

registry.category("web_tour.tours").add("mercas_ai_mcp_dashboard_tour", {
    steps: () => [
        {
            content: "The dashboard of the AI providers and tools",
            trigger: ".oi[data-icon=dns]",
        },
    ],
});
