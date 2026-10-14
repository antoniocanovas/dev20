import { ListRenderer } from "@web/views/list/list_renderer";
import { patch } from "@web/core/utils/patch";

patch(ListRenderer.prototype, {
    // ArrowDown/ArrowUp in editable lists (edit mode): move to same column next/prev row.
    onCellKeydownEditMode(hotkey, cell, group, record) {
        if (hotkey === "arrowdown" || hotkey === "arrowup") {
            const { list } = this.props;
            const index = list.records.indexOf(record);
            const futureRecord =
                hotkey === "arrowdown"
                    ? list.records[index + 1]
                    : list.records[index - 1];

            if (futureRecord) {
                const columnName = cell.getAttribute("name");
                const column = this.columns.find((col) => col.name === columnName);

                list.leaveEditMode({ validate: true }).then((canProceed) => {
                    if (canProceed) {
                        if (column) {
                            this.cellToFocus = { column, record: futureRecord };
                        }
                        list.enterEditMode(futureRecord);
                    }
                });
                return true;
            }
        }
        return super.onCellKeydownEditMode(hotkey, cell, group, record);
    },

    // ArrowDown/ArrowUp in read-only lists: move focus to the same column on the next/prev row.
    onCellKeydown(hotkey, cell, group, record) {
        if (hotkey === "arrowdown" || hotkey === "arrowup") {
            const records = this.props.list.records;
            const index = records.indexOf(record);
            const target =
                hotkey === "arrowdown" ? records[index + 1] : records[index - 1];

            if (target) {
                const columnName = cell.getAttribute("name");
                const selector = columnName ? `td[name="${columnName}"]` : "td:first-child";
                const rows = this.el.querySelectorAll("tr.o_data_row");
                const targetRow = rows[records.indexOf(target)];
                if (targetRow) {
                    const targetCell = targetRow.querySelector(selector) || targetRow.querySelector("td");
                    targetCell?.focus();
                }
                return true;
            }
        }
        return super.onCellKeydown(hotkey, cell, group, record);
    },
});
