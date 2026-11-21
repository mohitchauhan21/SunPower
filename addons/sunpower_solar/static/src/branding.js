/** @odoo-module **/
// Back office tab title: "SunPower - <screen>" instead of the engine's default name.
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { WebClient } from "@web/webclient/webclient";

patch(WebClient.prototype, {
    setup() {
        super.setup();
        useService("title").setParts({ zopenerp: "SunPower" });
    },
});
