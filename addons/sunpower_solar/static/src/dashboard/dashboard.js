/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const fmt = (v) =>
    new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(v || 0);

export class SolarDashboard extends Component {
    static template = "sunpower_solar.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ period: "month", data: null, loading: true });
        this.fmt = fmt;
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.data = await this.orm.call("solar.dashboard", "get_data", [this.state.period]);
        this.state.loading = false;
    }

    async setPeriod(p) {
        this.state.period = p;
        await this.load();
    }

    open(model, domain, name, views = [[false, "list"], [false, "form"]]) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: model,
            name, domain, views });
    }
    openRecord(model, id) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: model,
            res_id: id, views: [[false, "form"]] });
    }
    openAction(xmlid) {
        this.action.doAction(xmlid);
    }
    share() {
        this.action.doAction("sunpower_solar.action_solar_director_report", {
            additionalContext: { default_period: this.state.period },
        });
    }
}

registry.category("actions").add("sunpower_solar.dashboard", SolarDashboard);
