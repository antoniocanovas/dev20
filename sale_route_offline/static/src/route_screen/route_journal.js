import { browser } from "@web/core/browser/browser";
import { user } from "@web/core/user";
import { session } from "@web/session";

/**
 * Orders and payments made on this tablet: the ones not sent yet, and the orders of the day, so
 * that they can be reviewed and confirmed later.
 *
 * The offline plugin has the queue of calls, but no public way to list it. An entry is "synced"
 * once the server confirms that it has its last version (`revision`).
 *
 * Entry: { uuid, kind: "order"|"payment", partnerId, day: "YYYY-MM-DD", timeStamp, revision,
 *          synced, displayName, details: [str], order?: { confirmed, lines: [...] } }
 */
export class RouteJournal {
    constructor() {
        this.key = `sale_route_offline.journal.${session.db}.${user.userId}`;
    }

    /** @returns {Object[]} entries, oldest first */
    list() {
        try {
            return JSON.parse(browser.localStorage.getItem(this.key) || "[]");
        } catch {
            return [];
        }
    }

    get(uuid) {
        return this.list().find((entry) => entry.uuid === uuid);
    }

    save(entry) {
        const entries = this.list();
        const index = entries.findIndex((e) => e.uuid === entry.uuid);
        if (index === -1) {
            entries.push(entry);
        } else {
            entries[index] = entry;
        }
        this._write(entries);
    }

    /**
     * Marks as synced the entries whose last version reached the server, and forgets the synced
     * entries of the previous days.
     *
     * @param {Object} status {uuid: revision} as returned by the server
     * @param {string} today
     */
    update(status, today) {
        const entries = this.list().map((entry) =>
            status[entry.uuid] >= entry.revision ? { ...entry, synced: true } : entry
        );
        this._write(entries.filter((entry) => !entry.synced || entry.day === today));
    }

    _write(entries) {
        try {
            if (entries.length) {
                browser.localStorage.setItem(this.key, JSON.stringify(entries));
            } else {
                browser.localStorage.removeItem(this.key);
            }
        } catch {
            // Storage full or blocked: the queue of the offline plugin still has the call
        }
    }
}
